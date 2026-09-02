"""
Fetches Wikipedia data for each species in class_names.json.
Outputs:
  - wikipedia_fetch_results.json
  - needs_review.json
"""

import json
import re
import time
import requests


WIKI_API = "https://en.wikipedia.org/w/api.php"


session = requests.Session()

session.headers.update({
    "User-Agent": (
        "PlantChatbot/1.0 "
        "(educational project; "
        "contact: example@example.com)"
    ),
    "Accept": "application/json",
})


MANUAL_OVERRIDES = {
    "Llex cornuta": "Ilex cornuta",
    "Malushalliana": "Malus halliana",
    "Sabina chinensis cv. Pyramidalis": "Juniperus chinensis",
    "Flowering cherry": "Prunus serrulata",
    "Populus L": "Populus deltoides",
    "Platycladus orientalis Beverlevensis": "Platycladus orientalis",
    "Magnolia liliflora Desr": "Magnolia liliiflora",
    "Michelia figo (Lour.) Spreng": "Magnolia figo",
    "Juniperus chinensis Kaizuca": "Juniperus chinensis",
}


AUTHORITY_PATTERN = re.compile(
    r"\s+(L\.?|Lamb\.?|Desr\.?|Presl\.?|Brongn\.?|Lindl\.?)$"
)

VARIETY_PATTERN = re.compile(
    r"\s+(var\.|f\.|cv\.)\s+.*$"
)

PAREN_PATTERN = re.compile(
    r"\s*\([^)]*\)"
)


def clean_name(raw_label: str) -> str:

    if raw_label in MANUAL_OVERRIDES:
        return MANUAL_OVERRIDES[raw_label]

    name = raw_label.strip()

    name = PAREN_PATTERN.sub("", name)

    name = VARIETY_PATTERN.sub("", name)

    name = AUTHORITY_PATTERN.sub("", name)

    name = re.sub(r"\s+", " ", name)

    return name.strip()


def wiki_get(params: dict) -> requests.Response:
    """
    Sends a request to the Wikipedia API through the shared Session.
    """

    response = session.get(
        WIKI_API,
        params=params,
        timeout=20,
    )

    return response


def wiki_search_fallback(query: str) -> str | None:
    """
    Runs a search on Wikipedia when the direct page lookup fails.
    """

    response = wiki_get({
        "action": "query",
        "list": "search",
        "srsearch": query,
        "format": "json",
        "srlimit": 1,
    })

    response.raise_for_status()

    results = response.json().get(
        "query", {}
    ).get(
        "search", []
    )

    if results:
        return results[0]["title"]

    return None


def fetch_article(title: str) -> dict | None:
    """
    Fetches a Wikipedia article.
    """

    response = wiki_get({
        "action": "query",
        "prop": "extracts",
        "exintro": 1,
        "explaintext": 1,
        "titles": title,
        "format": "json",
    })

    response.raise_for_status()

    pages = response.json().get(
        "query", {}
    ).get(
        "pages", {}
    )

    page = next(
        iter(pages.values()),
        None
    )

    if page is None or "missing" in page:
        return None

    lead = page.get(
        "extract",
        ""
    ).strip()

    if not lead:
        return None

    response_full = wiki_get({
        "action": "query",
        "prop": "extracts",
        "explaintext": 1,
        "titles": title,
        "format": "json",
    })

    response_full.raise_for_status()

    pages_full = response_full.json().get(
        "query", {}
    ).get(
        "pages", {}
    )

    page_full = next(
        iter(pages_full.values()),
        None
    )

    full_text = (
        page_full.get("extract", "").strip()
        if page_full
        else ""
    )

    if full_text.startswith(lead):
        body = full_text[len(lead):].strip()
    else:
        body = full_text

    resolved_title = page.get(
        "title",
        title
    )

    return {
        "resolved_title": resolved_title,
        "summary": lead,
        "body": body,
        "url": (
            "https://en.wikipedia.org/wiki/"
            + resolved_title.replace(" ", "_")
        ),
    }


def resolve_species(raw_label: str) -> dict:
    """
    Matches a class label to a Wikipedia article.
    """

    cleaned = clean_name(raw_label)

    article = fetch_article(cleaned)

    status = "exact"

    if article is None:

        fallback_title = wiki_search_fallback(
            cleaned
        )

        if fallback_title:

            article = fetch_article(
                fallback_title
            )

            status = "search_fallback"

    if article is None:

        return {
            "label": raw_label,
            "cleaned_query": cleaned,
            "status": "NOT_FOUND",
        }

    return {
        "label": raw_label,
        "cleaned_query": cleaned,
        "status": status,
        **article,
    }


def main():

    with open(
        "class_names.json",
        "r",
        encoding="utf-8"
    ) as f:

        labels = json.load(f)

    results = []

    for label in labels:

        print(
            f"\nSearching Wikipedia: {label}"
        )

        try:

            result = resolve_species(
                label
            )

        except requests.HTTPError as e:

            print(
                f"❌ HTTP error: {label} -> {e}"
            )

            result = {
                "label": label,
                "cleaned_query": clean_name(label),
                "status": "REQUEST_ERROR",
                "error": str(e),
            }

        except requests.RequestException as e:

            print(
                f"❌ Network error: {label} -> {e}"
            )

            result = {
                "label": label,
                "cleaned_query": clean_name(label),
                "status": "REQUEST_ERROR",
                "error": str(e),
            }

        except Exception as e:

            print(
                f"❌ Unexpected error: {label} -> {e}"
            )

            result = {
                "label": label,
                "cleaned_query": clean_name(label),
                "status": "REQUEST_ERROR",
                "error": str(e),
            }

        results.append(result)

        icon = {
            "exact": "✅",
            "search_fallback": "⚠️",
            "NOT_FOUND": "❌",
            "REQUEST_ERROR": "❌",
        }.get(
            result["status"],
            "❌"
        )

        target = result.get(
            "resolved_title",
            result.get(
                "cleaned_query",
                "-"
            )
        )

        print(
            f"{icon} "
            f"{label:45s} -> {target}"
        )

        time.sleep(0.5)

    with open(
            "../wikipedia_fetch_results.json",
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            results,
            f,
            ensure_ascii=False,
            indent=2
        )

    needs_review = [
        result
        for result in results
        if result["status"] != "exact"
    ]

    with open(
            "../needs_review.json",
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            needs_review,
            f,
            ensure_ascii=False,
            indent=2
        )

    exact_count = len(results) - len(
        needs_review
    )

    print(
        f"\n{exact_count}/{len(results)} "
        f"matched exactly."
    )

    print(
        f"{len(needs_review)} entries "
        f"need review "
        f"-> needs_review.json"
    )


if __name__ == "__main__":
    main()