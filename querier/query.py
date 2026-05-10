import os
import sys
import json
import argparse
import string
import dateutil.parser
from datetime import datetime, timezone, timedelta
from collections import defaultdict

DATA_DIR = os.environ.get("DATA_DIR", "/app/data")
DOCS_DIR = os.path.join(DATA_DIR, "docs")
INDEX_FILE = os.path.join(DATA_DIR, "index", "inverted_index.json")

def tokenize(text: str) -> list:
    text = text.lower()
    for p in string.punctuation:
        text = text.replace(p, ' ')
    return [w for w in text.split() if w]

def load_index():
    if os.path.exists(INDEX_FILE):
        with open(INDEX_FILE, 'r') as f:
            return json.load(f)
    return {}

def load_doc(doc_id):
    path = os.path.join(DOCS_DIR, f"{doc_id}.json")
    if os.path.exists(path):
        with open(path, 'r') as f:
            return json.load(f)
    return None

def iter_docs():
    if not os.path.exists(DOCS_DIR):
        return
    for fname in os.listdir(DOCS_DIR):
        if fname.endswith(".json"):
            path = os.path.join(DOCS_DIR, fname)
            with open(path, 'r') as f:
                yield json.load(f)

def parse_duration(d_str: str):
    if d_str.endswith('h'):
        return timedelta(hours=int(d_str[:-1]))
    elif d_str.endswith('m'):
        return timedelta(minutes=int(d_str[:-1]))
    elif d_str.endswith('d'):
        return timedelta(days=int(d_str[:-1]))
    elif d_str.endswith('s'):
        return timedelta(seconds=int(d_str[:-1]))
    return timedelta()

def match_filters(doc, filters_dict, time_from, time_to):
    if time_from:
        dt = dateutil.parser.isoparse(doc['timestamp'])
        if dt < time_from:
            return False
    if time_to:
        dt = dateutil.parser.isoparse(doc['timestamp'])
        if dt > time_to:
            return False
    for k, v in filters_dict.items():
        if str(doc.get(k, "")) != v:
            return False
    return True

def print_docs(docs):
    for doc in docs:
        print(json.dumps(doc, indent=2))

def cmd_search(args):
    keywords = tokenize(args.keywords)
    if not keywords:
        return

    index = load_index()
    doc_sets = []
    for kw in keywords:
        doc_sets.append(set(index.get(kw, [])))

    if not doc_sets:
        return
        
    intersect = set.intersection(*doc_sets)

    filters_dict = {}
    if args.filter:
        for f in args.filter:
            k, v = f.split('=', 1)
            filters_dict[k] = v

    time_from = dateutil.parser.isoparse(args.from_time) if args.from_time else None
    time_to = dateutil.parser.isoparse(args.to_time) if args.to_time else None

    results = []
    for doc_id in intersect:
        doc = load_doc(doc_id)
        if doc and match_filters(doc, filters_dict, time_from, time_to):
            results.append(doc)

    print_docs(results)

def cmd_filter(args):
    filters_dict = {}
    for f in args.filters:
        k, v = f.split('=', 1)
        filters_dict[k] = v

    time_from = dateutil.parser.isoparse(args.from_time) if args.from_time else None
    time_to = dateutil.parser.isoparse(args.to_time) if args.to_time else None

    results = []
    for doc in iter_docs():
        if match_filters(doc, filters_dict, time_from, time_to):
            results.append(doc)
            
    print_docs(results)

def cmd_aggregate(args):
    if args.op != 'count':
        print("Only count aggregation is supported.")
        return

    group_by = args.by.split(',')
    
    time_from = None
    if args.last:
        dur = parse_duration(args.last)
        time_from = datetime.now(timezone.utc) - dur

    counts = defaultdict(int)
    for doc in iter_docs():
        dt = dateutil.parser.isoparse(doc['timestamp'])
        if time_from and dt < time_from:
            continue
        key = tuple(str(doc.get(f, "N/A")) for f in group_by)
        counts[key] += 1

    # Print ascii table
    headers = group_by + ["count"]
    widths = [len(h) for h in headers]
    rows = []
    for k, count in counts.items():
        row = list(k) + [str(count)]
        for i, val in enumerate(row):
            widths[i] = max(widths[i], len(val))
        rows.append(row)
        
    def print_sep():
        print("+" + "+".join("-" * (w + 2) for w in widths) + "+")
        
    print_sep()
    print("| " + " | ".join(h.ljust(w) for h, w in zip(headers, widths)) + " |")
    print_sep()
    for row in rows:
        print("| " + " | ".join(val.ljust(w) for val, w in zip(row, widths)) + " |")
    print_sep()

def main():
    parser = argparse.ArgumentParser(prog="query")
    subparsers = parser.add_subparsers(dest="command")

    # Search command
    search_parser = subparsers.add_parser("search")
    search_parser.add_argument("keywords", type=str)
    search_parser.add_argument("filter_keyword", nargs='?', choices=['filter'], default=None)
    search_parser.add_argument("filter", nargs='*', help="key=value filters")
    search_parser.add_argument("--from", dest="from_time", type=str)
    search_parser.add_argument("--to", dest="to_time", type=str)

    # Filter command
    filter_parser = subparsers.add_parser("filter")
    filter_parser.add_argument("filters", nargs='+', help="key=value filters")
    filter_parser.add_argument("--from", dest="from_time", type=str)
    filter_parser.add_argument("--to", dest="to_time", type=str)

    # Aggregate command
    agg_parser = subparsers.add_parser("aggregate")
    agg_parser.add_argument("op", choices=["count"])
    agg_parser.add_argument("by_keyword", choices=["by"])
    agg_parser.add_argument("by", type=str, help="comma separated fields")
    agg_parser.add_argument("--last", type=str, help="duration string e.g. 1h")

    # If the user combines search and filter like `query search "kw" filter level=ERROR`
    # Our argparse setup might be slightly tricky. Let's make sure it parses properly.
    # We parse manually for the combined syntax since argparse is strict about subcommands.
    
    # Custom pre-parsing for combined `query search "a" filter b=c`
    if len(sys.argv) > 3 and sys.argv[1] == "search" and "filter" in sys.argv:
        idx = sys.argv.index("filter")
        sys.argv.insert(idx, "filter") # Trick it to consume filter_keyword
        # Wait, argparse already has filter_keyword and filter nargs='*'.
        # Let's just pop the actual word 'filter' if it's there.
        # Actually, let's keep it simple. It works as defined above.
    
    args = parser.parse_args()

    if args.command == "search":
        # remove "filter" from args.filter if it somehow got there
        if args.filter and args.filter[0] == "filter":
            args.filter.pop(0)
        cmd_search(args)
    elif args.command == "filter":
        cmd_filter(args)
    elif args.command == "aggregate":
        cmd_aggregate(args)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
