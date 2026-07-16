import json
import os

import requests
from dotenv import load_dotenv

load_dotenv(".env")

API_KEY = os.getenv("BRANDFOLDER_API_KEY")
COLLECTION_ID = "gss8kc28x4vhgwxk9s3cj3"


def main() -> None:
    if not API_KEY:
        raise RuntimeError(
            "BRANDFOLDER_API_KEY nav norādīts .env failā."
        )

    response = requests.get(
        (
            "https://brandfolder.com/api/v4/"
            f"collections/{COLLECTION_ID}/assets"
        ),
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Accept": "application/json",
        },
        params={
            "search": "7032",
            "include": "attachments,custom_fields",
            "per": 100,
        },
        timeout=90,
    )

    print("HTTP Status:", response.status_code)

    if not response.ok:
        print(response.text)
        response.raise_for_status()

    payload = response.json()

    print("Atrasti aktīvi:", len(payload.get("data", [])))
    print(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()