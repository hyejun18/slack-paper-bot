"""Slack event handling and message posting module."""

import hashlib
import hmac
import logging
import time
from typing import Any

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

logger = logging.getLogger(__name__)


class SlackError(Exception):
    """Exception raised for Slack-related errors."""

    pass


class SlackHandler:
    """Handle Slack events and post messages."""

    def __init__(
        self,
        bot_token: str,
        signing_secret: str,
        channel_ids: list[str],
        max_retries: int = 3,
        retry_delay: int = 2,
    ):
        """
        Initialize Slack handler.

        Args:
            bot_token: Slack Bot User OAuth Token
            signing_secret: Slack Signing Secret for request verification
            channel_ids: List of channel IDs to monitor
            max_retries: Number of retries for API calls
            retry_delay: Seconds between retries
        """
        self.client = WebClient(token=bot_token)
        self.signing_secret = signing_secret
        self.channel_ids = set(channel_ids)
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.bot_user_id: str | None = None

        # Cache processed events to avoid duplicates
        self._processed_events: set[str] = set()
        self._max_cache_size = 1000

        logger.info(f"Initialized Slack handler for channels: {channel_ids}")

    def verify_request(self, timestamp: str, body: bytes, signature: str) -> bool:
        """
        Verify that a request came from Slack.

        Args:
            timestamp: X-Slack-Request-Timestamp header
            body: Raw request body
            signature: X-Slack-Signature header

        Returns:
            True if valid, False otherwise
        """
        # Check timestamp to prevent replay attacks (5 minutes tolerance)
        try:
            ts = int(timestamp)
            if abs(time.time() - ts) > 300:
                logger.warning("Request timestamp too old")
                return False
        except ValueError:
            return False

        # Compute expected signature
        sig_basestring = f"v0:{timestamp}:{body.decode('utf-8')}"
        expected_sig = (
            "v0="
            + hmac.new(
                self.signing_secret.encode(),
                sig_basestring.encode(),
                hashlib.sha256,
            ).hexdigest()
        )

        # Compare signatures
        return hmac.compare_digest(expected_sig, signature)

    def get_bot_user_id(self) -> str:
        """Get the bot's user ID."""
        if self.bot_user_id is None:
            try:
                response = self.client.auth_test()
                self.bot_user_id = response["user_id"]
                logger.info(f"Bot user ID: {self.bot_user_id}")
            except SlackApiError as e:
                raise SlackError(f"Failed to get bot user ID: {e}")
        return self.bot_user_id

    def should_process_event(self, event: dict[str, Any]) -> bool:
        """
        Check if an event should be processed.

        Args:
            event: Slack event data

        Returns:
            True if event should be processed
        """
        # Check channel
        channel = event.get("channel")
        if channel not in self.channel_ids:
            logger.debug(f"Ignoring event from channel: {channel}")
            return False

        # Avoid processing our own messages
        user = event.get("user")
        if user == self.get_bot_user_id():
            logger.debug("Ignoring own message")
            return False

        # Check for duplicate events
        event_id = event.get("client_msg_id") or event.get("event_ts")
        if event_id:
            if event_id in self._processed_events:
                logger.debug(f"Duplicate event: {event_id}")
                return False
            self._processed_events.add(event_id)

            # Trim cache if too large
            if len(self._processed_events) > self._max_cache_size:
                self._processed_events = set(list(self._processed_events)[-500:])

        return True

    def extract_pdf_files(self, event: dict[str, Any]) -> list[dict[str, Any]]:
        """
        Extract PDF file information from a message event.

        Args:
            event: Slack message event

        Returns:
            List of PDF file info dicts with url_private and name
        """
        files = event.get("files", [])
        pdf_files = []

        for file in files:
            if file.get("filetype") == "pdf" or file.get("name", "").lower().endswith(".pdf"):
                pdf_files.append(
                    {
                        "id": file.get("id"),
                        "name": file.get("name"),
                        "url_private": file.get("url_private"),
                        "size": file.get("size"),
                    }
                )
                logger.info(f"Found PDF: {file.get('name')}")

        return pdf_files

    def get_file_download_headers(self) -> dict[str, str]:
        """Get headers needed to download files from Slack."""
        return {"Authorization": f"Bearer {self.client.token}"}

    def add_reaction(self, channel: str, timestamp: str, emoji: str = "party_blob") -> bool:
        """
        Add an emoji reaction to a message.

        Args:
            channel: Channel ID
            timestamp: Message timestamp
            emoji: Emoji name without colons (default: party_blob)

        Returns:
            True if successful, False otherwise
        """
        try:
            self.client.reactions_add(
                channel=channel,
                timestamp=timestamp,
                name=emoji,
            )
            logger.info(f"Added :{emoji}: reaction to message")
            return True
        except SlackApiError as e:
            # Ignore "already_reacted" error
            if e.response.get("error") == "already_reacted":
                logger.debug(f"Already reacted with :{emoji}:")
                return True
            logger.warning(f"Failed to add reaction: {e}")
            return False

    def post_thread_reply(
        self,
        channel: str,
        thread_ts: str,
        text: str,
        blocks: list[dict] | None = None,
    ) -> dict[str, Any]:
        """
        Post a reply in a thread.

        Args:
            channel: Channel ID
            thread_ts: Parent message timestamp
            text: Message text
            blocks: Optional Block Kit blocks

        Returns:
            Slack API response

        Raises:
            SlackError: If posting fails after all retries
        """
        last_error = None

        for attempt in range(1, self.max_retries + 1):
            try:
                logger.info(f"Posting reply (attempt {attempt}/{self.max_retries})")

                response = self.client.chat_postMessage(
                    channel=channel,
                    thread_ts=thread_ts,
                    text=text,
                    blocks=blocks,
                    unfurl_links=False,
                    unfurl_media=False,
                )

                logger.info(f"Posted reply to thread {thread_ts}")
                return response.data

            except SlackApiError as e:
                last_error = e
                logger.warning(f"Attempt {attempt} failed: {e}")

                # Don't retry on certain errors
                if e.response.get("error") in ["channel_not_found", "not_in_channel"]:
                    raise SlackError(f"Cannot post to channel: {e.response.get('error')}")

                if attempt < self.max_retries:
                    time.sleep(self.retry_delay * attempt)

        raise SlackError(f"Failed to post message after {self.max_retries} attempts: {last_error}")

    def post_processing_status(
        self,
        channel: str,
        thread_ts: str,
        filename: str,
        status: str = "processing",
    ) -> str | None:
        """
        Post a status message while processing.

        Args:
            channel: Channel ID
            thread_ts: Parent message timestamp
            filename: Name of the file being processed
            status: Status type (processing, error)

        Returns:
            Message timestamp if posted, None otherwise
        """
        if status == "processing":
            text = f"`{filename}` 논문을 분석 중입니다..."
        elif status == "error":
            text = f"`{filename}` 처리 중 오류가 발생했습니다."
        else:
            text = f"처리 상태: {status}"

        try:
            response = self.client.chat_postMessage(
                channel=channel,
                thread_ts=thread_ts,
                text=text,
            )
            return response.get("ts")
        except SlackApiError as e:
            logger.warning(f"Failed to post status: {e}")
            return None

    def update_message(
        self,
        channel: str,
        ts: str,
        text: str,
        blocks: list[dict] | None = None,
    ) -> None:
        """
        Update an existing message.

        Args:
            channel: Channel ID
            ts: Message timestamp to update
            text: New message text
            blocks: Optional Block Kit blocks
        """
        try:
            self.client.chat_update(
                channel=channel,
                ts=ts,
                text=text,
                blocks=blocks,
            )
        except SlackApiError as e:
            logger.warning(f"Failed to update message: {e}")

    def delete_message(self, channel: str, ts: str) -> None:
        """
        Delete a message.

        Args:
            channel: Channel ID
            ts: Message timestamp to delete
        """
        try:
            self.client.chat_delete(channel=channel, ts=ts)
        except SlackApiError as e:
            logger.warning(f"Failed to delete message: {e}")

    def format_summary_blocks(self, summary: str, filename: str) -> list[dict]:
        """
        Format summary text as Slack Block Kit blocks.

        Args:
            summary: Summary text in markdown
            filename: Original filename

        Returns:
            List of Block Kit blocks
        """
        # Split summary into sections if too long (Slack limit: 3000 chars per block)
        max_block_length = 2900
        blocks = []

        # Header
        blocks.append(
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"논문 요약: {filename[:50]}{'...' if len(filename) > 50 else ''}",
                    "emoji": True,
                },
            }
        )

        blocks.append({"type": "divider"})

        # Split content into chunks
        if len(summary) <= max_block_length:
            blocks.append(
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": summary},
                }
            )
        else:
            # Split by double newlines (paragraphs)
            paragraphs = summary.split("\n\n")
            current_chunk = ""

            for para in paragraphs:
                if len(current_chunk) + len(para) + 2 <= max_block_length:
                    current_chunk += para + "\n\n"
                else:
                    if current_chunk:
                        blocks.append(
                            {
                                "type": "section",
                                "text": {"type": "mrkdwn", "text": current_chunk.strip()},
                            }
                        )
                    current_chunk = para + "\n\n"

            if current_chunk:
                blocks.append(
                    {
                        "type": "section",
                        "text": {"type": "mrkdwn", "text": current_chunk.strip()},
                    }
                )

        # Footer
        blocks.append({"type": "divider"})
        blocks.append(
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": "_이 요약은 AI(Google Gemini)에 의해 자동 생성되었습니다. 정확성을 보장하지 않으므로 원문을 확인해주세요._",
                    }
                ],
            }
        )

        return blocks
