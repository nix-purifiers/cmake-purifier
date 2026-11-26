# SPDX-License-Identifier: MIT
#
# Runs the HTTP handlers of the lock run on its HTTP record (record.py),
# for assemble.py, and test_handlers.py checks it with stand-in handlers.
# A handler follows the handler protocol of the purifier library
# (tools/http_records.py there): it reads the record as JSON lines and
# prints the URLs it claims and the download entries that replace them.
import json
import subprocess


class HandlerError(Exception):
    pass


def apply_handlers(responses, programs):
    """The responses no handler claimed, and the entries of the handlers.

    Each program sees the responses that the programs before it left
    unclaimed. Its entries are download entries of the purifier library,
    at the paths the replay serves: files with a `url`, and inline
    entries with their `contents`."""
    entries = []
    for program in programs:
        stdin = "".join(json.dumps(response, sort_keys=True) + "\n" for response in responses)
        result = subprocess.run([program], input=stdin, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            raise HandlerError(f"the HTTP handler {program} failed: {result.stderr.strip()}")
        try:
            output = json.loads(result.stdout)
            claimed = set(output["claimed"])
            handled = output["entries"]
        except (ValueError, KeyError, TypeError) as error:
            raise HandlerError(f"the HTTP handler {program} printed no claimed URLs and entries: {error}") from error
        for entry in handled:
            if "path" not in entry or ("url" in entry) == ("contents" in entry):
                raise HandlerError(f"the HTTP handler {program} printed an entry that is neither a file nor inline: {entry}")
        responses = [response for response in responses if response["url"] not in claimed]
        entries.extend(handled)
    return responses, entries
