"""
Slack Paper Bot - Automatic biology paper summarizer

This bot monitors Slack channels for PDF uploads and automatically
summarizes biology papers in Korean using Google Gemini API.
"""

import asyncio
import logging
import sys
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from logging.handlers import RotatingFileHandler
from pathlib import Path

import uvicorn
from fastapi import BackgroundTasks, FastAPI, HTTPException, Request, Response

from modules.config import get_config
from modules.pdf_parser import PDFParseError, PDFParser
from modules.slack_handler import SlackError, SlackHandler
from modules.summarizer import PaperSummarizer, SummaryError

# Global instances
config = None
slack_handler = None
pdf_parser = None
summarizer = None
executor = None
logger = logging.getLogger("slack-paper-bot")


def setup_logging() -> None:
    """Configure logging based on config."""
    log_level = getattr(logging, config.log_level.upper(), logging.INFO)

    # Create formatter
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    root_logger.addHandler(console_handler)

    # File handler if configured
    if config.log_file:
        log_path = Path(config.log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        file_handler = RotatingFileHandler(
            log_path,
            maxBytes=config.log_max_size_mb * 1024 * 1024,
            backupCount=config.log_backup_count,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

    logger.info(f"Logging configured at level: {config.log_level}")


def initialize_components() -> None:
    """Initialize all bot components."""
    global slack_handler, pdf_parser, summarizer, executor

    logger.info("Initializing components...")

    slack_handler = SlackHandler(
        bot_token=config.slack_bot_token,
        signing_secret=config.slack_signing_secret,
        channel_ids=config.slack_channel_ids,
        max_retries=config.max_retries,
        retry_delay=config.retry_delay,
    )

    pdf_parser = PDFParser(
        max_pages=config.summary_max_pages,
        timeout=config.timeout,
    )

    summarizer = PaperSummarizer(
        api_key=config.gemini_api_key,
        model=config.gemini_model,
        detail_level=config.summary_detail_level,
        max_retries=config.max_retries,
        retry_delay=config.retry_delay,
        cache_enabled=config.summary_enable_cache,
        cache_dir=config.summary_cache_dir,
    )

    # Thread pool for blocking operations
    executor = ThreadPoolExecutor(max_workers=4)

    logger.info("All components initialized successfully")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    global config

    # Startup
    config = get_config()

    # Validate configuration
    errors = config.validate()
    if errors:
        for error in errors:
            print(f"Configuration error: {error}", file=sys.stderr)
        sys.exit(1)

    setup_logging()
    initialize_components()

    logger.info("Slack Paper Bot started")

    yield

    # Shutdown
    logger.info("Shutting down...")
    if executor:
        executor.shutdown(wait=True)


app = FastAPI(
    title="Slack Paper Bot",
    description="Automatic biology paper summarizer for Slack",
    version="1.0.0",
    lifespan=lifespan,
)


def process_pdf_sync(
    channel: str,
    thread_ts: str,
    pdf_url: str,
    filename: str,
    status_ts: str | None,
) -> None:
    """
    Synchronous PDF processing function (runs in thread pool).

    Args:
        channel: Slack channel ID
        thread_ts: Thread timestamp for reply
        pdf_url: URL to download PDF
        filename: Original filename
        status_ts: Status message timestamp to update/delete
    """
    try:
        # Download and extract text
        logger.info(f"Processing PDF: {filename}")
        headers = slack_handler.get_file_download_headers()
        text = pdf_parser.extract_from_url(pdf_url, headers)

        # Generate summary
        logger.info(f"Generating summary for: {filename}")
        summary = summarizer.summarize(text)

        # Format and post reply
        blocks = slack_handler.format_summary_blocks(summary, filename)

        # Delete status message if exists
        if status_ts:
            slack_handler.delete_message(channel, status_ts)

        # Post summary
        slack_handler.post_thread_reply(
            channel=channel,
            thread_ts=thread_ts,
            text=summary[:3000],  # Fallback text
            blocks=blocks,
        )

        logger.info(f"Successfully posted summary for: {filename}")

    except PDFParseError as e:
        logger.error(f"PDF parsing error for {filename}: {e}")
        error_message = f"PDF 파싱 오류: {e}\n\n파일이 손상되었거나 텍스트 추출이 불가능한 형식일 수 있습니다."

        if status_ts:
            slack_handler.update_message(channel, status_ts, error_message)
        else:
            slack_handler.post_thread_reply(channel, thread_ts, error_message)

    except SummaryError as e:
        logger.error(f"Summary error for {filename}: {e}")
        error_message = f"요약 생성 오류: {e}\n\nAPI 할당량을 확인하거나 잠시 후 다시 시도해주세요."

        if status_ts:
            slack_handler.update_message(channel, status_ts, error_message)
        else:
            slack_handler.post_thread_reply(channel, thread_ts, error_message)

    except SlackError as e:
        logger.error(f"Slack error for {filename}: {e}")

    except Exception as e:
        logger.exception(f"Unexpected error processing {filename}: {e}")
        try:
            error_message = f"처리 중 예상치 못한 오류가 발생했습니다: {type(e).__name__}"
            if status_ts:
                slack_handler.update_message(channel, status_ts, error_message)
            else:
                slack_handler.post_thread_reply(channel, thread_ts, error_message)
        except Exception:
            pass


async def process_pdf_async(
    channel: str,
    thread_ts: str,
    pdf_url: str,
    filename: str,
    status_ts: str | None,
) -> None:
    """Async wrapper for PDF processing."""
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(
        executor,
        process_pdf_sync,
        channel,
        thread_ts,
        pdf_url,
        filename,
        status_ts,
    )


@app.post("/slack/events")
async def slack_events(request: Request, background_tasks: BackgroundTasks):
    """
    Handle Slack Event API webhooks.

    This endpoint receives all events from Slack and processes PDF uploads.
    """
    # Get request data
    body = await request.body()
    timestamp = request.headers.get("X-Slack-Request-Timestamp", "")
    signature = request.headers.get("X-Slack-Signature", "")

    # Verify request
    if not slack_handler.verify_request(timestamp, body, signature):
        logger.warning("Invalid Slack request signature")
        raise HTTPException(status_code=401, detail="Invalid signature")

    # Parse JSON
    try:
        data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    # Handle URL verification challenge
    if data.get("type") == "url_verification":
        logger.info("Handling URL verification challenge")
        return {"challenge": data.get("challenge")}

    # Handle events
    if data.get("type") == "event_callback":
        event = data.get("event", {})
        event_type = event.get("type")

        logger.debug(f"Received event: {event_type}, data: {event}")

        # Handle file_shared event
        if event_type == "file_shared":
            file_id = event.get("file_id")
            channel = event.get("channel_id")

            if channel not in slack_handler.channel_ids:
                logger.debug(f"Ignoring file from channel: {channel}")
                return Response(status_code=200)

            # Check for duplicate file_shared events
            if file_id in slack_handler._processed_events:
                logger.debug(f"Duplicate file_shared event: {file_id}")
                return Response(status_code=200)
            slack_handler._processed_events.add(file_id)

            # Get file info from Slack API
            try:
                file_info = slack_handler.client.files_info(file=file_id)
                file_data = file_info.get("file", {})

                if file_data.get("filetype") == "pdf" or file_data.get("name", "").lower().endswith(".pdf"):
                    filename = file_data.get("name", "unknown.pdf")
                    pdf_url = file_data.get("url_private")

                    # Get the message timestamp for thread reply
                    shares = file_data.get("shares", {})
                    # Try public channels first, then private
                    channel_shares = shares.get("public", {}).get(channel) or shares.get("private", {}).get(channel)
                    thread_ts = channel_shares[0].get("ts") if channel_shares else event.get("event_ts")

                    logger.info(f"Found PDF via file_shared: {filename}")

                    # Add reaction to the original message
                    slack_handler.add_reaction(channel, thread_ts, "party_blob")

                    # Post processing status
                    status_ts = slack_handler.post_processing_status(
                        channel=channel,
                        thread_ts=thread_ts,
                        filename=filename,
                    )

                    # Process PDF in background
                    background_tasks.add_task(
                        process_pdf_async,
                        channel,
                        thread_ts,
                        pdf_url,
                        filename,
                        status_ts,
                    )

                    logger.info(f"Queued PDF for processing: {filename}")
            except Exception as e:
                logger.error(f"Failed to get file info: {e}")

            return Response(status_code=200)

        # Note: message events with files are handled via file_shared event above

    # Always respond quickly to Slack
    return Response(status_code=200)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "version": "1.0.0",
        "channels": list(slack_handler.channel_ids) if slack_handler else [],
    }


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "name": "Slack Paper Bot",
        "description": "Automatic biology paper summarizer",
        "endpoints": {
            "/slack/events": "Slack Event API webhook",
            "/health": "Health check",
        },
    }


def main():
    """Run the application."""
    global config
    config = get_config()

    # Validate early
    errors = config.validate()
    if errors:
        for error in errors:
            print(f"Configuration error: {error}", file=sys.stderr)
        sys.exit(1)

    # SSL configuration
    ssl_config = {}
    if config.ssl_enabled:
        ssl_config = {
            "ssl_keyfile": config.ssl_key_file,
            "ssl_certfile": config.ssl_cert_file,
        }
        print(f"SSL enabled with cert: {config.ssl_cert_file}")

    print(f"Starting server on {config.server_host}:{config.server_port}")

    uvicorn.run(
        "main:app",
        host=config.server_host,
        port=config.server_port,
        reload=False,
        log_level="info",
        **ssl_config,
    )


if __name__ == "__main__":
    main()
