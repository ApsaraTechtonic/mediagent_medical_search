import requests
import xml.etree.ElementTree as ET
def search_medlineplus(query, max_results=5):
    """Search the official MedlinePlus health-topic service and return source-backed snippets."""
    endpoint = "https://wsearch.nlm.nih.gov/ws/query"
    try:
        response = requests.get(
            endpoint,
            params={"db": "healthTopics", "term": query, "retmax": max_results},
            timeout=15,
            headers={"User-Agent": "MediAgentAI-HackathonPrototype/1.0"},
        )
        response.raise_for_status()
        root = ET.fromstring(response.content)
    except requests.exceptions.Timeout as exc:
        raise RuntimeError("MedlinePlus search timed out. Please try again.") from exc
    except requests.exceptions.RequestException as exc:
        raise RuntimeError(
            "Could not reach MedlinePlus. Check your internet connection and try again. "
            "No uncited answer was generated."
        ) from exc
    except ET.ParseError as exc:
        raise RuntimeError("MedlinePlus returned an unexpected response. Please try again.") from exc

    results = []
    for doc in root.findall(".//document"):
        # MedlinePlus returns the URL as a document attribute, but the title
        # and summary are child <content> elements (names are case-sensitive).
        url = (doc.attrib.get("url") or "").strip()
        title = ""
        summary = ""
        snippet = ""
        for content in doc.findall("content"):
            name = (content.attrib.get("name") or "").lower()
            text_value = " ".join("".join(content.itertext()).split())
            if name == "title" and text_value:
                title = text_value
            elif name == "fullsummary" and text_value and not summary:
                summary = text_value
            elif name == "snippet" and text_value and not snippet:
                snippet = text_value

        if title and url:
            results.append({
                "title": title,
                "url": url,
                "summary": (summary or snippet)[:1800],
            })
        if len(results) >= max_results:
            break
    return results

