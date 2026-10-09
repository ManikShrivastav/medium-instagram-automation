import os
import json
import re
import html
import urllib.request
import urllib.parse
import urllib.error
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path

FEED_URL = "https://medium.com/feed/@manikshrivastav36"
STATE_FILE = Path("processed.json")
API_VERSION = os.getenv("META_API_VERSION", "v22.0")
GRAPH_URL = f"https://graph.facebook.com/{API_VERSION}"


class ImageParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.images = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() == "img":
            attrs = dict(attrs)
            src = attrs.get("src") or attrs.get("data-src")
            if src and src.startswith("https://"):
                self.images.append(src)


def get_url(url, data=None):
    encoded = None
    if data is not None:
        encoded = urllib.parse.urlencode(data).encode()
    request = urllib.request.Request(
        url,
        data=encoded,
        headers={"User-Agent": "MediumInstagramBot/1.0"}
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read()


def get_articles():
    xml_data = get_url(FEED_URL)
    root = ET.fromstring(xml_data)
    ns = {
        "content": "http://purl.org/rss/1.0/modules/content/"
    }

    articles = []
    for item in root.findall("./channel/item"):
        link = (item.findtext("link") or "").strip()
        title = (item.findtext("title") or "").strip()
        if not link or not title:
            continue

        content = item.findtext("content:encoded", namespaces=ns) or ""
        description = item.findtext("description") or ""
        parser = ImageParser()
        parser.feed(html.unescape(content or description))

        image_url = parser.images[0] if parser.images else None
        articles.append({
            "id": link,
            "title": title,
            "url": link,
            "image": image_url,
        })

    return articles


def read_state():
    if not STATE_FILE.exists():
        return None
    return json.loads(STATE_FILE.read_text())


def save_state(processed):
    STATE_FILE.write_text(
        json.dumps(sorted(processed), indent=2) + "\n"
    )


def publish_instagram(article):
    token = os.environ["META_ACCESS_TOKEN"]
    instagram_id = os.environ["INSTAGRAM_USER_ID"]
    fixed_caption = os.environ["FIXED_CAPTION"].strip()

    image_url = article["image"]
    if not image_url:
        raise RuntimeError(
            f"No image found in Medium RSS for: {article['url']}"
        )

    caption = f"{fixed_caption}\n\n{article['url']}"
    if len(caption) > 2200:
        raise RuntimeError("Instagram caption exceeds 2,200 characters.")

    # Step 1: Create the Instagram image container.
    container = json.loads(get_url(
        f"{GRAPH_URL}/{instagram_id}/media",
        {
            "image_url": image_url,
            "caption": caption,
            "access_token": token,
        }
    ))

    container_id = container.get("id")
    if not container_id:
        raise RuntimeError(f"Meta did not return a media container: {container}")

    # Step 2: Check that Instagram has finished processing the image.
    import time
    for _ in range(12):
        status = json.loads(get_url(
            f"{GRAPH_URL}/{container_id}",
            {
                "fields": "status_code",
                "access_token": token,
            }
        ))
        status_code = status.get("status_code")
        if status_code == "FINISHED":
            break
        if status_code == "ERROR":
            raise RuntimeError(f"Instagram image processing failed: {status}")
        time.sleep(5)
    else:
        raise RuntimeError("Instagram image processing timed out.")

    # Step 3: Publish the post.
    result = json.loads(get_url(
        f"{GRAPH_URL}/{instagram_id}/media_publish",
        {
            "creation_id": container_id,
            "access_token": token,
        }
    ))

    if not result.get("id"):
        raise RuntimeError(f"Instagram did not confirm publishing: {result}")

    print(f"Published: {article['title']} — {article['url']}")


def main():
    articles = get_articles()
    if not articles:
        print("No articles found in the Medium feed.")
        return

    processed = read_state()

    # First run: establish a baseline so old articles aren't reposted.
    if processed is None:
        save_state({article["id"] for article in articles})
        print("Initial baseline saved. No old articles were published.")
        return

    processed = set(processed)

    # Medium RSS normally lists newest first. Publish new articles oldest first.
    new_articles = [
        article for article in reversed(articles)
        if article["id"] not in processed
    ]

    if not new_articles:
        print("No new Medium articles.")
        return

    for article in new_articles:
        publish_instagram(article)
        processed.add(article["id"])
        save_state(processed)


if __name__ == "__main__":
    main()
