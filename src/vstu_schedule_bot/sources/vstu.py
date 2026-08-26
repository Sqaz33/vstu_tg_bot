from __future__ import annotations

import fnmatch
import hashlib
from html.parser import HTMLParser
from urllib.parse import urljoin

import aiohttp

from vstu_schedule_bot.domain.models import DownloadedFile, SourceFile


class SourceFileNotFoundError(LookupError):
    pass


class _LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, str]] = []
        self._href: str | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        attributes = dict(attrs)
        href = attributes.get("href")
        if href:
            self._href = href
            self._text = []

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "a" and self._href is not None:
            label = " ".join("".join(self._text).split())
            self.links.append((self._href, label))
            self._href = None
            self._text = []


def _decode_html(content: bytes, charset: str | None) -> str:
    encodings = [charset, "utf-8", "windows-1251"]
    for encoding in encodings:
        if not encoding:
            continue
        try:
            return content.decode(encoding)
        except (LookupError, UnicodeDecodeError):
            continue
    return content.decode("utf-8", errors="replace")


class VstuSourceClient:
    def __init__(
        self,
        session: aiohttp.ClientSession,
        page_url: str,
        file_pattern: str,
    ) -> None:
        self._session = session
        self._page_url = page_url
        self._file_pattern = " ".join(file_pattern.split()).casefold()

    async def discover_file(self) -> SourceFile:
        async with self._session.get(self._page_url) as response:
            response.raise_for_status()
            content = await response.read()
            html = _decode_html(content, response.charset)

        parser = _LinkParser()
        parser.feed(html)
        candidates: list[SourceFile] = []
        for href, label in parser.links:
            normalized = " ".join(label.split()).casefold()
            if not href.lower().split("?", maxsplit=1)[0].endswith((".xls", ".xlsx", ".xlsm")):
                continue
            if fnmatch.fnmatch(normalized, self._file_pattern):
                candidates.append(SourceFile(label=label, url=urljoin(self._page_url, href)))
        if not candidates:
            labels = [
                label for _, label in parser.links if label.lower().endswith((".xls", ".xlsx"))
            ]
            available = ", ".join(labels[:8]) or "none"
            raise SourceFileNotFoundError(
                f"File matching {self._file_pattern!r} was not found; available: {available}"
            )
        return candidates[0]

    async def download(
        self,
        source: SourceFile,
        *,
        etag: str | None = None,
        last_modified: str | None = None,
    ) -> DownloadedFile:
        headers: dict[str, str] = {}
        if etag:
            headers["If-None-Match"] = etag
        if last_modified:
            headers["If-Modified-Since"] = last_modified

        async with self._session.get(source.url, headers=headers) as response:
            if response.status == 304:
                return DownloadedFile(
                    source=source,
                    content=b"",
                    sha256="",
                    etag=etag,
                    last_modified=last_modified,
                    not_modified=True,
                )
            response.raise_for_status()
            content = await response.read()
            if not content:
                raise ValueError(f"VSTU returned an empty schedule file: {source.url}")
            return DownloadedFile(
                source=source,
                content=content,
                sha256=hashlib.sha256(content).hexdigest(),
                etag=response.headers.get("ETag"),
                last_modified=response.headers.get("Last-Modified"),
            )
