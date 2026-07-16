import os

import requests
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("BRANDFOLDER_API_KEY")
API_BASE_URL = "https://brandfolder.com/api/v4"

ASSET_ID = "jgmpbx4f5nskmxpmnnkgjm"


def main() -> None:
    if not API_KEY:
        raise RuntimeError(
            "BRANDFOLDER_API_KEY nav norādīts .env failā."
        )

    response = requests.get(
        f"{API_BASE_URL}/assets/{ASSET_ID}/attachments",
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Accept": "application/json",
        },
        params={
            "fields": (
                "best_metadata,"
                "other_metadata,"
                "thumbnail_url,"
                "extension,"
                "extracted_colors,"
                "best_guess_background_color,"
                "extract_document_text"
            )
        },
        timeout=60,
    )

    print(f"HTTP Status: {response.status_code}")

    if not response.ok:
        print(response.text)
        response.raise_for_status()

    payload = response.json()
    attachments = payload.get("data", [])

    print(f"Atrasti pielikumi: {len(attachments)}")

    for attachment in attachments:
        attributes = attachment.get("attributes", {})

        print("-" * 70)
        print(f"Attachment ID: {attachment.get('id', '')}")
        print(f"Nosaukums:     {attributes.get('filename', '')}")
        print(f"Paplašinājums: {attributes.get('extension', '')}")
        print(f"Thumbnail URL: {attributes.get('thumbnail_url', '')}")
        print(f"CDN URL:       {attributes.get('cdn_url', '')}")
        print(f"Download URL:  {attributes.get('url', '')}")


if __name__ == "__main__":
    main()