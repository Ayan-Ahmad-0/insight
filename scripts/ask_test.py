import json
import sys
import urllib.error
import urllib.request

def main():
    token, question = sys.argv[1], sys.argv[2]
    url = sys.argv[3] if len(sys.argv) > 3 else "http://localhost:8765/v1/ask"

    req = urllib.request.Request(
        url,
        data=json.dumps({"question": question}).encode(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            print(json.dumps(json.load(r), indent=2))
    except urllib.error.HTTPError as e:
        print(e.code, e.read().decode())


if __name__ == "__main__":
    main()