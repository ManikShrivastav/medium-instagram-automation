import os
import json
import urllib.parse
import urllib.request
import urllib.error

version = os.getenv("META_API_VERSION", "v26.0")
token = os.environ["META_ACCESS_TOKEN"]
expected_id = os.environ["INSTAGRAM_USER_ID"]

params = urllib.parse.urlencode({
    "fields": "user_id,username",
    "access_token": token,
})

url = f"https://graph.instagram.com/{version}/me?{params}"
request = urllib.request.Request(
    url,
    headers={"User-Agent": "MediumInstagramBot/1.0"}
)

try:
    with urllib.request.urlopen(request, timeout=30) as response:
        result = json.loads(response.read())

    actual_id = str(result.get("user_id", result.get("id", "")))
    username = result.get("username", "unknown")

    print(f"Instagram username: @{username}")
    print(f"Instagram account ID returned: {actual_id}")

    if not actual_id:
        raise RuntimeError(
            "No Instagram account ID returned. Check API response fields."
        )

    if actual_id != expected_id:
        raise RuntimeError(
            "The returned account ID does not match INSTAGRAM_USER_ID. "
            "Update the GitHub secret with the correct ID."
        )

    print("SUCCESS: Token works and account ID matches.")

except urllib.error.HTTPError as error:
    print(f"Instagram API returned HTTP {error.code}.")
    print(error.read().decode("utf-8", errors="replace"))
    raise
