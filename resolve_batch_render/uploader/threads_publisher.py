"""Threads video publish via graph.threads.net (Meta Threads API)."""

from __future__ import annotations

import os
import random
import re
import time
from dataclasses import dataclass

import httpx
from loguru import logger

from uploader.meta_accounts import MetaPublishTarget, threads_targets


class ThreadsPublishError(RuntimeError):
    pass


@dataclass(frozen=True)
class ThreadsPublishResult:
    account: str
    threads_user_id: str
    container_id: str
    post_id: str


def _env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def _mask(s: str, keep: int = 6) -> str:
    raw = (s or "").strip()
    if len(raw) <= keep * 2:
        return "***"
    return f"{raw[:keep]}…{raw[-keep:]}"


def build_threads_text(caption: str, *, max_chars: int = 480) -> str:
    """
    Threads Reels text: short body + exactly ONE tour link.

    Caption already often contains CAPTION_SUFFIX with the tour URL — do not
    append BRAND_SITE a second time. Never truncate mid-URL.
    """
    tour = _env(
        "BRAND_SITE",
        "https://jayshambo.com/tours/kai-las-svyaschennaya-kora-iz-lhasy",
    )
    raw = (caption or "").strip()
    # Drop brand links block (Сайт / Instagram / Telegram / YouTube)
    raw = re.split(r"\n\n(?=Сайт:)", raw, maxsplit=1)[0].strip()

    urls = re.findall(r"https?://\S+", raw)
    # Prefer existing tour link from caption; else BRAND_SITE
    keep = next(
        (u.rstrip(".,);") for u in urls if "jayshambo.com/tours/" in u),
        "",
    ) or tour

    body = re.sub(r"https?://\S+", "", raw)
    # Drop duplicated CTA / empty "Программа: …" URL line leftovers
    body = re.sub(r"\n{3,}", "\n\n", body).strip()
    body = re.sub(r"[ \t]+\n", "\n", body)
    # If body already has a code-word CTA, drop a trailing standalone duplicate.
    if re.search(r"напиши.*кайлас", body, flags=re.IGNORECASE):
        body = re.sub(
            r"\n+Напиши\s*[«\"]?КАЙЛАС[»\"]?\s*$",
            "",
            body,
            flags=re.IGNORECASE,
        ).strip()
    if re.search(r"напиши.*ретрит", body, flags=re.IGNORECASE):
        body = re.sub(
            r"\n+Напиши\s*[«\"]?РЕТРИТ[»\"]?\s*$",
            "",
            body,
            flags=re.IGNORECASE,
        ).strip()

    has_own_cta = bool(
        re.search(r"напиши\s*[«\"']?(КАЙЛАС|РЕТРИТ)", body, flags=re.IGNORECASE)
    )
    cta = "" if has_own_cta else "\n\nНапиши «КАЙЛАС»"
    suffix = f"{cta}\n\n{keep}".rstrip()
    budget = max_chars - len(suffix)
    if budget < 80:
        # Extreme: keep link only
        return keep[:max_chars]
    if len(body) > budget:
        body = body[: budget - 1].rstrip(" \n.") + "…"
    text = f"{body}{suffix}".strip()
    # Hard guarantee: at most one URL
    found = re.findall(r"https?://\S+", text)
    if len(found) > 1:
        for extra in found[1:]:
            text = text.replace(extra, "", 1)
        text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text[:max_chars]


def build_threads_carousel_text(caption: str, *, max_chars: int = 480) -> str:
    """
    Carousel → site article pipeline: keep short summary + exactly ONE link
    (the blog URL already in caption). Do not append tour/BRAND_SITE.
    """
    raw = (caption or "").strip()
    # Drop Reels-style brand block / tour CTAs if present
    raw = re.split(r"\n\n(?=Сайт:)", raw, maxsplit=1)[0].strip()
    raw = re.sub(
        r"\n\nНапиши\s*[«\"]?КАЙЛАС[»\"]?\s*",
        "\n\n",
        raw,
        flags=re.IGNORECASE,
    ).strip()
    # Prefer jayshambo.com/blog link; else first http link
    urls = re.findall(r"https?://\S+", raw)
    blog = next((u for u in urls if "jayshambo.com/blog/" in u), None)
    keep = blog or (urls[0] if urls else "")
    # Strip ALL urls from body, then re-attach the single keep link
    body = re.sub(r"https?://\S+", "", raw)
    body = re.sub(
        r"(Хотите больше деталей\s*[—\-–]?\s*читайте на сайте\s*:?\s*)$",
        "",
        body,
        flags=re.IGNORECASE | re.MULTILINE,
    )
    body = re.sub(r"\n{3,}", "\n\n", body).strip()
    # Soft trim
    reserve = len(keep) + 60 if keep else 0
    budget = max_chars - reserve
    if len(body) > budget:
        body = body[: max(0, budget - 1)].rstrip() + "…"
    if keep:
        text = f"{body}\n\nХотите больше деталей — читайте на сайте:\n{keep}"
    else:
        text = body
    # Hard guarantee: at most one URL
    found = re.findall(r"https?://\S+", text)
    if len(found) > 1:
        for extra in found[1:]:
            text = text.replace(extra, "", 1)
        text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text[:max_chars]


def publish_threads_video(
    *,
    target: MetaPublishTarget,
    video_url: str,
    caption: str,
) -> ThreadsPublishResult:
    """
    Two-step Threads publish: create VIDEO container → wait → threads_publish.
    Docs: https://developers.facebook.com/docs/threads/posts/
    """
    user_id = (target.threads_user_id or "").strip()
    token = (target.threads_token or target.page_token or "").strip()
    if not user_id or not token:
        raise ThreadsPublishError(
            f"{target.label}: missing META_N_THREADS_USER_ID / THREADS_TOKEN"
        )

    api_ver = _env("THREADS_API_VERSION", "v1.0")
    base = f"https://graph.threads.net/{api_ver}"
    text = build_threads_text(caption)
    label = target.label

    logger.info(
        f"[Threads] account={label} user={user_id} action=create_container "
        f"video_url={video_url} text_len={len(text)}"
    )

    with httpx.Client(timeout=120.0) as client:
        time.sleep(random.uniform(1.0, 2.5))
        r1 = client.post(
            f"{base}/{user_id}/threads",
            params={"access_token": token},
            data={
                "media_type": "VIDEO",
                "video_url": video_url,
                "text": text,
                "access_token": token,
            },
        )
        if r1.status_code >= 400:
            raise ThreadsPublishError(
                f"Threads create failed ({r1.status_code}): {r1.text}"
            )
        container_id = str(r1.json().get("id") or "").strip()
        if not container_id:
            raise ThreadsPublishError(f"Threads create missing id: {r1.text}")

        # Poll container status (video processing)
        deadline = time.time() + float(_env("THREADS_CONTAINER_WAIT_SEC", "180") or 180)
        status = ""
        while time.time() < deadline:
            time.sleep(random.uniform(4.0, 8.0))
            st = client.get(
                f"{base}/{container_id}",
                params={"fields": "status,error_message", "access_token": token},
            )
            if st.status_code >= 400:
                logger.warning(
                    f"[Threads] status poll failed ({st.status_code}): {st.text[:200]}"
                )
                continue
            data = st.json()
            status = str(data.get("status") or "").strip().upper()
            logger.info(
                f"[Threads] account={label} container={container_id} status={status}"
            )
            if status in {"FINISHED", "PUBLISHED"}:
                break
            if status in {"ERROR", "EXPIRED"}:
                raise ThreadsPublishError(
                    f"Threads container {status}: {data.get('error_message') or data}"
                )

        if status not in {"FINISHED", "PUBLISHED"}:
            # Docs allow publish after ~30s even if status field sparse
            logger.warning(
                f"[Threads] account={label} proceeding to publish "
                f"(last_status={status!r})"
            )

        time.sleep(random.uniform(1.5, 3.0))
        r2 = client.post(
            f"{base}/{user_id}/threads_publish",
            params={"access_token": token},
            data={"creation_id": container_id, "access_token": token},
        )
        if r2.status_code >= 400:
            raise ThreadsPublishError(
                f"Threads publish failed ({r2.status_code}): {r2.text}"
            )
        post_id = str(r2.json().get("id") or "").strip()
        if not post_id:
            raise ThreadsPublishError(f"Threads publish missing id: {r2.text}")

    logger.success(
        f"[Threads] account={label} published post_id={post_id} "
        f"container={container_id} token={_mask(token)}"
    )
    return ThreadsPublishResult(
        account=label,
        threads_user_id=user_id,
        container_id=container_id,
        post_id=post_id,
    )


def publish_threads_carousel(
    *,
    target: MetaPublishTarget,
    image_urls: list[str],
    caption: str,
) -> ThreadsPublishResult:
    """
    Three-step Threads carousel: IMAGE items → CAROUSEL container → publish.
    Docs: https://developers.facebook.com/docs/threads/posts/
    """
    urls = [u.strip() for u in image_urls if (u or "").strip()]
    if len(urls) < 2:
        raise ThreadsPublishError("Threads carousel requires at least 2 images")
    if len(urls) > 20:
        raise ThreadsPublishError("Threads carousel supports at most 20 images")

    user_id = (target.threads_user_id or "").strip()
    token = (target.threads_token or target.page_token or "").strip()
    if not user_id or not token:
        raise ThreadsPublishError(
            f"{target.label}: missing META_N_THREADS_USER_ID / THREADS_TOKEN"
        )

    api_ver = _env("THREADS_API_VERSION", "v1.0")
    base = f"https://graph.threads.net/{api_ver}"
    text = build_threads_carousel_text(caption)
    label = target.label
    link_count = len(re.findall(r"https?://\S+", text))

    logger.info(
        f"[Threads carousel] account={label} user={user_id} "
        f"slides={len(urls)} text_len={len(text)} links={link_count}"
    )

    with httpx.Client(timeout=120.0) as client:
        child_ids: list[str] = []
        for i, image_url in enumerate(urls, start=1):
            time.sleep(random.uniform(1.2, 3.0))
            logger.info(
                f"[Threads carousel] account={label} action=create_item "
                f"slide={i}/{len(urls)}"
            )
            r_item = client.post(
                f"{base}/{user_id}/threads",
                params={"access_token": token},
                data={
                    "media_type": "IMAGE",
                    "image_url": image_url,
                    "is_carousel_item": "true",
                    "access_token": token,
                },
            )
            if r_item.status_code >= 400:
                raise ThreadsPublishError(
                    f"Threads carousel item {i} failed "
                    f"({r_item.status_code}): {r_item.text}"
                )
            child_id = str(r_item.json().get("id") or "").strip()
            if not child_id:
                raise ThreadsPublishError(
                    f"Threads carousel item {i} missing id: {r_item.text}"
                )
            child_ids.append(child_id)

        time.sleep(random.uniform(1.5, 3.5))
        r_parent = client.post(
            f"{base}/{user_id}/threads",
            params={"access_token": token},
            data={
                "media_type": "CAROUSEL",
                "children": ",".join(child_ids),
                "text": text,
                "access_token": token,
            },
        )
        if r_parent.status_code >= 400:
            raise ThreadsPublishError(
                f"Threads carousel container failed "
                f"({r_parent.status_code}): {r_parent.text}"
            )
        container_id = str(r_parent.json().get("id") or "").strip()
        if not container_id:
            raise ThreadsPublishError(
                f"Threads carousel container missing id: {r_parent.text}"
            )

        deadline = time.time() + float(_env("THREADS_CONTAINER_WAIT_SEC", "180") or 180)
        status = ""
        while time.time() < deadline:
            time.sleep(random.uniform(4.0, 8.0))
            st = client.get(
                f"{base}/{container_id}",
                params={"fields": "status,error_message", "access_token": token},
            )
            if st.status_code >= 400:
                logger.warning(
                    f"[Threads carousel] status poll failed "
                    f"({st.status_code}): {st.text[:200]}"
                )
                continue
            data = st.json()
            status = str(data.get("status") or "").strip().upper()
            logger.info(
                f"[Threads carousel] account={label} "
                f"container={container_id} status={status}"
            )
            if status in {"FINISHED", "PUBLISHED"}:
                break
            if status in {"ERROR", "EXPIRED"}:
                raise ThreadsPublishError(
                    f"Threads carousel {status}: "
                    f"{data.get('error_message') or data}"
                )

        if status not in {"FINISHED", "PUBLISHED"}:
            logger.warning(
                f"[Threads carousel] account={label} proceeding to publish "
                f"(last_status={status!r})"
            )

        time.sleep(random.uniform(1.5, 3.0))
        r2 = client.post(
            f"{base}/{user_id}/threads_publish",
            params={"access_token": token},
            data={"creation_id": container_id, "access_token": token},
        )
        if r2.status_code >= 400:
            raise ThreadsPublishError(
                f"Threads carousel publish failed ({r2.status_code}): {r2.text}"
            )
        post_id = str(r2.json().get("id") or "").strip()
        if not post_id:
            raise ThreadsPublishError(
                f"Threads carousel publish missing id: {r2.text}"
            )

    logger.success(
        f"[Threads carousel] account={label} published post_id={post_id} "
        f"container={container_id}"
    )
    return ThreadsPublishResult(
        account=label,
        threads_user_id=user_id,
        container_id=container_id,
        post_id=post_id,
    )


def publish_threads_text(
    *,
    target: MetaPublishTarget,
    text: str,
) -> ThreadsPublishResult:
    """Publish a TEXT-only Threads post (no video/carousel)."""
    user_id = (target.threads_user_id or "").strip()
    token = (target.threads_token or target.page_token or "").strip()
    if not user_id or not token:
        raise ThreadsPublishError(
            f"{target.label}: missing META_N_THREADS_USER_ID / THREADS_TOKEN"
        )

    body = (text or "").strip()
    if not body:
        raise ThreadsPublishError("Empty text")
    # Threads API hard cap is 500; never clip mid-word.
    if len(body) > 500:
        from uploader.threads_prompts import fit_threads_text

        body = fit_threads_text(body, max_chars=500)

    api_ver = _env("THREADS_API_VERSION", "v1.0")
    base = f"https://graph.threads.net/{api_ver}"
    label = target.label
    link_count = len(re.findall(r"https?://\S+", body))

    logger.info(
        f"[Threads TEXT] account={label} user={user_id} "
        f"chars={len(body)} links={link_count}"
    )

    with httpx.Client(timeout=120.0) as client:
        time.sleep(random.uniform(1.0, 2.5))
        r1 = client.post(
            f"{base}/{user_id}/threads",
            params={"access_token": token},
            data={
                "media_type": "TEXT",
                "text": body,
                "access_token": token,
            },
        )
        if r1.status_code >= 400:
            raise ThreadsPublishError(
                f"Threads TEXT create failed ({r1.status_code}): {r1.text}"
            )
        container_id = str(r1.json().get("id") or "").strip()
        if not container_id:
            raise ThreadsPublishError(f"Threads TEXT create missing id: {r1.text}")

        deadline = time.time() + float(_env("THREADS_CONTAINER_WAIT_SEC", "180") or 180)
        status = ""
        while time.time() < deadline:
            time.sleep(random.uniform(2.0, 5.0))
            st = client.get(
                f"{base}/{container_id}",
                params={"fields": "status,error_message", "access_token": token},
            )
            if st.status_code >= 400:
                continue
            data = st.json()
            status = str(data.get("status") or "").strip().upper()
            if status in {"FINISHED", "PUBLISHED"}:
                break
            if status in {"ERROR", "EXPIRED"}:
                raise ThreadsPublishError(
                    f"Threads TEXT container {status}: {data.get('error_message') or data}"
                )

        time.sleep(random.uniform(1.5, 3.0))
        r2 = client.post(
            f"{base}/{user_id}/threads_publish",
            params={"access_token": token},
            data={"creation_id": container_id, "access_token": token},
        )
        if r2.status_code >= 400:
            raise ThreadsPublishError(
                f"Threads TEXT publish failed ({r2.status_code}): {r2.text}"
            )
        post_id = str(r2.json().get("id") or "").strip()
        if not post_id:
            raise ThreadsPublishError(f"Threads TEXT publish missing id: {r2.text}")

    logger.success(
        f"[Threads TEXT] account={label} published post_id={post_id} "
        f"container={container_id}"
    )
    return ThreadsPublishResult(
        account=label,
        threads_user_id=user_id,
        container_id=container_id,
        post_id=post_id,
    )


def publish_threads_reply(
    *,
    target: MetaPublishTarget,
    reply_to_id: str,
    text: str,
) -> ThreadsPublishResult:
    """Publish a text reply under a comment on our own Threads post."""
    user_id = (target.threads_user_id or "").strip()
    token = (target.threads_token or target.page_token or "").strip()
    parent_id = (reply_to_id or "").strip()
    if not user_id or not token:
        raise ThreadsPublishError(
            f"{target.label}: missing META_N_THREADS_USER_ID / THREADS_TOKEN"
        )
    if not parent_id:
        raise ThreadsPublishError("reply_to_id is empty")

    body = (text or "").strip()
    if not body:
        raise ThreadsPublishError("Empty reply text")
    if len(body) > 500:
        body = body[:497].rstrip(" ,.;") + "…"

    api_ver = _env("THREADS_API_VERSION", "v1.0")
    base = f"https://graph.threads.net/{api_ver}"
    label = target.label
    logger.info(
        f"[Threads reply] account={label} user={user_id} "
        f"reply_to={parent_id} chars={len(body)}"
    )

    with httpx.Client(timeout=120.0) as client:
        time.sleep(random.uniform(1.2, 2.8))
        created = client.post(
            f"{base}/{user_id}/threads",
            params={"access_token": token},
            data={
                "media_type": "TEXT",
                "text": body,
                "reply_to_id": parent_id,
                "access_token": token,
            },
        )
        if created.status_code >= 400:
            raise ThreadsPublishError(
                f"Threads reply create failed ({created.status_code}): {created.text}"
            )
        container_id = str(created.json().get("id") or "").strip()
        if not container_id:
            raise ThreadsPublishError(
                f"Threads reply create missing id: {created.text}"
            )

        deadline = time.time() + float(_env("THREADS_CONTAINER_WAIT_SEC", "180") or 180)
        status = ""
        while time.time() < deadline:
            time.sleep(random.uniform(2.0, 4.5))
            polled = client.get(
                f"{base}/{container_id}",
                params={"fields": "status,error_message", "access_token": token},
            )
            if polled.status_code >= 400:
                continue
            data = polled.json()
            status = str(data.get("status") or "").strip().upper()
            if status in {"FINISHED", "PUBLISHED"}:
                break
            if status in {"ERROR", "EXPIRED"}:
                raise ThreadsPublishError(
                    f"Threads reply container {status}: "
                    f"{data.get('error_message') or data}"
                )

        time.sleep(random.uniform(1.5, 3.2))
        published = client.post(
            f"{base}/{user_id}/threads_publish",
            params={"access_token": token},
            data={"creation_id": container_id, "access_token": token},
        )
        if published.status_code >= 400:
            raise ThreadsPublishError(
                f"Threads reply publish failed ({published.status_code}): "
                f"{published.text}"
            )
        post_id = str(published.json().get("id") or "").strip()
        if not post_id:
            raise ThreadsPublishError(
                f"Threads reply publish missing id: {published.text}"
            )

    logger.success(
        f"[Threads reply] account={label} published post_id={post_id} "
        f"reply_to={parent_id}"
    )
    return ThreadsPublishResult(
        account=label,
        threads_user_id=user_id,
        container_id=container_id,
        post_id=post_id,
    )


def publish_all_threads(
    *,
    video_url: str,
    caption: str,
) -> list[ThreadsPublishResult]:
    targets = threads_targets()
    if not targets:
        return []
    stagger_lo = float(_env("UPLOAD_ACCOUNT_STAGGER_MIN", "2") or 2)
    stagger_hi = float(_env("UPLOAD_ACCOUNT_STAGGER_MAX", "12") or 12)
    out: list[ThreadsPublishResult] = []
    for i, t in enumerate(targets):
        if i > 0:
            delay = random.uniform(stagger_lo, stagger_hi) * 60.0
            logger.info(f"[Threads] stagger before {t.label}: {delay/60:.1f} min")
            time.sleep(delay)
        try:
            out.append(
                publish_threads_video(target=t, video_url=video_url, caption=caption)
            )
        except Exception as e:
            logger.error(f"[Threads] account={t.label} failed: {type(e).__name__}: {e}")
            # Don't kill IG success — soft-fail per account
            continue
    return out


def publish_all_threads_carousels(
    *,
    image_urls: list[str],
    caption: str,
    meta_index: int | None = None,
) -> list[ThreadsPublishResult]:
    """Publish carousel to Threads targets (default: all with PUBLISH_THREADS)."""
    targets = threads_targets()
    if meta_index is not None:
        from uploader.meta_accounts import load_meta_targets

        targets = [
            t
            for t in load_meta_targets()
            if t.index == meta_index and t.publish_threads
        ]
    if not targets:
        logger.warning("[Threads carousel] no publish targets")
        return []
    out: list[ThreadsPublishResult] = []
    for i, t in enumerate(targets):
        if i > 0:
            time.sleep(random.uniform(8.0, 25.0))
        try:
            out.append(
                publish_threads_carousel(
                    target=t, image_urls=image_urls, caption=caption
                )
            )
        except Exception as e:
            logger.error(
                f"[Threads carousel] account={t.label} failed: "
                f"{type(e).__name__}: {e}"
            )
            continue
    return out
