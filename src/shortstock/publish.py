"""Optional publishing through Buffer.

Buffer only accepts media by public URL, so videos are first uploaded to S3-compatible storage
(AWS S3, Cloudflare R2, Backblaze B2, MinIO...). Everything here is opt-in: without a Buffer
key shortstock just renders files for you to download.
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

import httpx

from shortstock import db
from shortstock.config import get_setting

logger = logging.getLogger(__name__)

BUFFER_URL = "https://api.buffer.com"
PublishMode = Literal["queue", "now", "schedule", "draft"]


class PublishError(RuntimeError):
    pass


# ── storage ──────────────────────────────────────────────────────────────────


def storage_configured() -> bool:
    return all(get_setting(k) for k in ("s3_bucket", "s3_access_key_id", "s3_secret_access_key"))


def upload_public(path: Path, key: str) -> str:
    """Upload a file and return a URL Buffer can fetch."""
    if not storage_configured():
        raise PublishError("Set up S3-compatible storage in Settings so Buffer can fetch the video")
    import boto3

    client = boto3.client(
        "s3",
        endpoint_url=get_setting("s3_endpoint_url") or None,
        region_name=get_setting("s3_region") or None,
        aws_access_key_id=get_setting("s3_access_key_id"),
        aws_secret_access_key=get_setting("s3_secret_access_key"),
    )
    bucket = get_setting("s3_bucket")
    client.upload_file(str(path), bucket, key, ExtraArgs={"ContentType": "video/mp4"})
    base = get_setting("s3_public_base_url").rstrip("/")
    if base:
        return f"{base}/{key}"
    return client.generate_presigned_url(
        "get_object", Params={"Bucket": bucket, "Key": key}, ExpiresIn=7 * 24 * 3600
    )


# ── Buffer ───────────────────────────────────────────────────────────────────


class BufferClient:
    def __init__(self, api_key: str | None = None, transport: httpx.BaseTransport | None = None):
        api_key = api_key if api_key is not None else get_setting("buffer_api_key")
        if not api_key:
            raise PublishError("Add your Buffer API key in Settings to publish")
        self._client = httpx.Client(
            base_url=BUFFER_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=60,
            transport=transport,
        )

    def query(self, query: str, variables: dict[str, Any] | None = None) -> dict:
        response = self._client.post("/", json={"query": query, "variables": variables or {}})
        if response.status_code >= 400:
            raise PublishError(f"Buffer error {response.status_code}: {response.text[:300]}")
        payload = response.json()
        if payload.get("errors"):
            raise PublishError(f"Buffer error: {payload['errors'][0].get('message')}")
        return payload["data"]

    def organizations(self) -> list[dict]:
        return self.query("query { account { organizations { id name } } }")["account"]["organizations"]

    def organization_id(self) -> str:
        configured = get_setting("buffer_organization_id")
        if configured:
            return configured
        orgs = self.organizations()
        if not orgs:
            raise PublishError("Your Buffer account has no organizations")
        return orgs[0]["id"]

    def channels(self) -> list[dict]:
        data = self.query(
            "query Channels($id: OrganizationId!) { channels(input: {organizationId: $id}) "
            "{ id name service avatar } }",
            {"id": self.organization_id()},
        )
        return data["channels"]

    def create_post(
        self,
        channel_id: str,
        service: str,
        text: str,
        video_url: str,
        title: str,
        mode: PublishMode,
        scheduled_at: datetime | None = None,
    ) -> str:
        post: dict[str, Any] = {
            "channelId": channel_id,
            "text": text,
            "schedulingType": "automatic",
            "assets": [{"video": {"url": video_url}}],
        }
        if mode == "draft":
            post["mode"] = "addToQueue"
            post["saveToDraft"] = True
        elif mode == "schedule":
            if scheduled_at is None:
                raise PublishError("Pick a time to schedule the post")
            post["mode"] = "customScheduled"
            post["dueAt"] = scheduled_at.isoformat()
        else:
            post["mode"] = "shareNow" if mode == "now" else "addToQueue"
        metadata = platform_metadata(service, title)
        if metadata:
            post["metadata"] = metadata
        data = self.query(
            "mutation CreatePost($input: CreatePostInput!) { createPost(input: $input) { "
            "__typename ... on PostActionSuccess { post { id status } } "
            "... on MutationError { message } } }",
            {"input": post},
        )["createPost"]
        if data.get("__typename") != "PostActionSuccess":
            raise PublishError(data.get("message") or f"Buffer returned {data.get('__typename')}")
        return data["post"]["id"]


def platform_metadata(service: str, title: str) -> dict | None:
    if service == "youtube":
        return {
            "youtube": {
                "title": title[:100],
                "categoryId": "22",
                "privacy": "public",
                "madeForKids": False,
                "notifySubscribers": True,
                "embeddable": True,
                "license": "youtube",
            }
        }
    if service == "instagram":
        return {"instagram": {"type": "reel", "shouldShareToFeed": True}}
    if service == "facebook":
        return {"facebook": {"type": "reel"}}
    return None


def post_text(video: dict) -> str:
    tags = " ".join(video.get("hashtags") or [])
    return f"{video['caption']}\n\n{tags}".strip() if tags else video["caption"]


def publish_video(
    video_id: str,
    channel_ids: list[str],
    mode: PublishMode = "queue",
    scheduled_at: datetime | None = None,
    text: str | None = None,
    title: str | None = None,
    client: BufferClient | None = None,
    uploader=upload_public,
) -> list[dict]:
    video = db.get_video(video_id)
    if video is None or not Path(video["file_path"]).exists():
        raise PublishError("That video is not ready to publish")
    client = client or BufferClient()
    channels = {c["id"]: c for c in client.channels()}
    unknown = [c for c in channel_ids if c not in channels]
    if unknown:
        raise PublishError(f"Unknown Buffer channel(s): {', '.join(unknown)}")

    path = Path(video["file_path"])
    media_url = uploader(path, f"shortstock/{video['run_id']}/{path.name}")
    results = []
    for channel_id in channel_ids:
        channel = channels[channel_id]
        record = {
            "video_id": video_id,
            "channel_id": channel_id,
            "channel_name": channel.get("name"),
            "service": channel.get("service"),
            "mode": mode,
            "media_url": media_url,
            "scheduled_at": scheduled_at.isoformat() if scheduled_at else None,
        }
        try:
            post_id = client.create_post(
                channel_id,
                channel.get("service", ""),
                text or post_text(video),
                media_url,
                title or video["title"],
                mode,
                scheduled_at,
            )
            results.append(db.create_post(**record, status="sent_to_buffer", buffer_post_id=post_id))
        except (PublishError, httpx.HTTPError) as exc:
            logger.warning("Buffer publish failed for %s: %s", channel_id, exc)
            results.append(db.create_post(**record, status="failed", error=str(exc)))
    return results
