import os

import requests
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("BRANDFOLDER_API_KEY")
API_BASE_URL = "https://brandfolder.com/api/v4"


def main() -> None:
    if not API_KEY:
        raise RuntimeError(
            "BRANDFOLDER_API_KEY nav norādīts .env failā."
        )

    response = requests.get(
        f"{API_BASE_URL}/brandfolders",
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Accept": "application/json",
        },
        params={"per": 100},
        timeout=60,
    )

    print(f"HTTP Status: {response.status_code}")

    if not response.ok:
        print(response.text)
        response.raise_for_status()

    payload = response.json()

    print("Atbildes tips:", type(payload).__name__)

    if not isinstance(payload, dict):
        print("Negaidīts atbildes formāts:")
        print(payload)
        return

    print("Galvenās atslēgas:", list(payload.keys()))

    data = payload.get("data", [])

    print("data tips:", type(data).__name__)

    if not isinstance(data, list):
        print("Negaidīts data formāts:")
        print(data)
        return

    print("Brandfolder skaits:", len(data))

    if not data:
        print("API atgrieza tukšu Brandfolder sarakstu.")
        return

    for item in data:
        attributes = item.get("attributes", {})

        print("-" * 60)
        print(f"Nosaukums: {attributes.get('name', '')}")
        print(f"Slug:      {attributes.get('slug', '')}")
        print(f"ID:        {item.get('id', '')}")


if __name__ == "__main__":
    main()