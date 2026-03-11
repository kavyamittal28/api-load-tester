import shlex
import json
import base64
from typing import Any, Dict, Optional


def parse_curl(curl_command: str) -> Dict[str, Any]:
    """Parse a cURL command string into its components."""
    curl_command = curl_command.strip()

    # Remove leading 'curl' keyword
    if curl_command.lower().startswith("curl "):
        curl_command = curl_command[5:]
    elif curl_command.lower() == "curl":
        raise ValueError("Empty cURL command — please provide a URL.")

    # Normalize line continuations (\\\n or \\\r\n)
    curl_command = curl_command.replace("\\\r\n", " ").replace("\\\n", " ")

    try:
        tokens = shlex.split(curl_command)
    except ValueError as e:
        raise ValueError(f"Could not parse cURL command: {e}")

    url: Optional[str] = None
    method: Optional[str] = None
    headers: Dict[str, str] = {}
    raw_body: Optional[str] = None
    verify_ssl = True

    i = 0
    while i < len(tokens):
        tok = tokens[i]

        if tok in ("-X", "--request"):
            i += 1
            if i < len(tokens):
                method = tokens[i].upper()

        elif tok in ("-H", "--header"):
            i += 1
            if i < len(tokens):
                key, _, val = tokens[i].partition(":")
                headers[key.strip()] = val.strip()

        elif tok in ("-d", "--data", "--data-raw", "--data-binary", "--data-ascii"):
            i += 1
            if i < len(tokens):
                raw_body = tokens[i]
                if method is None:
                    method = "POST"

        elif tok in ("-u", "--user"):
            i += 1
            if i < len(tokens):
                encoded = base64.b64encode(tokens[i].encode()).decode()
                headers["Authorization"] = f"Basic {encoded}"

        elif tok in ("-k", "--insecure"):
            verify_ssl = False

        elif tok in ("-L", "--location", "--compressed", "-s", "--silent",
                     "-v", "--verbose", "-i", "--include", "-I", "--head",
                     "-g", "--globoff"):
            pass  # flags we acknowledge but ignore

        elif tok in ("--url",):
            i += 1
            if i < len(tokens):
                url = tokens[i].strip("'\"")

        elif not tok.startswith("-"):
            # Bare argument is the URL
            url = tok.strip("'\"")

        else:
            # Unknown flag that might take a value — skip both conservatively
            # Only skip next token if it doesn't look like a flag itself
            if i + 1 < len(tokens) and not tokens[i + 1].startswith("-"):
                i += 1  # skip value

        i += 1

    if not url:
        raise ValueError("No URL found in cURL command.")

    # If method wasn't set, GET for no body, POST for body
    if method is None:
        method = "POST" if raw_body else "GET"

    # Try to parse body as JSON dict/list; fall back to raw string
    body: Any = None
    if raw_body:
        try:
            body = json.loads(raw_body)
        except (json.JSONDecodeError, ValueError):
            body = raw_body  # keep as plain string

    return {
        "url": url,
        "method": method,
        "headers": headers,
        "body": body,
        "raw_body": raw_body,
        "verify_ssl": verify_ssl,
    }
