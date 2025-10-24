#!/usr/bin/env python3
"""
Documentation generation script for ArenaLab API.

This script generates OpenAPI documentation and can export it to various formats.
"""

import json
import yaml
import argparse
from pathlib import Path
import sys

# Add the current directory to Python path
sys.path.insert(0, str(Path(__file__).parent))

from app import app


def generate_openapi_json(output_path: str = "openapi.json"):
    """Generate OpenAPI JSON documentation."""
    openapi_schema = app.openapi()
    
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(openapi_schema, f, indent=2, ensure_ascii=False)
    
    print(f"OpenAPI JSON documentation generated: {output_path}")
    return openapi_schema


def generate_openapi_yaml(output_path: str = "openapi.yaml"):
    """Generate OpenAPI YAML documentation."""
    openapi_schema = app.openapi()
    
    with open(output_path, "w", encoding="utf-8") as f:
        yaml.dump(openapi_schema, f, default_flow_style=False, allow_unicode=True)
    
    print(f"OpenAPI YAML documentation generated: {output_path}")
    return openapi_schema


def print_api_summary():
    """Print a summary of available API endpoints."""
    openapi_schema = app.openapi()
    paths = openapi_schema.get("paths", {})
    
    print("\n" + "="*60)
    print("ArenaLab API Endpoints Summary")
    print("="*60)
    
    for path, methods in paths.items():
        print(f"\n📍 {path}")
        for method, details in methods.items():
            method_upper = method.upper()
            summary = details.get("summary", "No summary")
            tags = details.get("tags", [])
            tag_str = f" [{', '.join(tags)}]" if tags else ""
            print(f"  {method_upper:6} - {summary}{tag_str}")
    
    print(f"\nTotal endpoints: {sum(len(methods) for methods in paths.values())}")
    print(f"Total paths: {len(paths)}")
    
    # Count by tags
    tag_counts = {}
    for methods in paths.values():
        for details in methods.values():
            for tag in details.get("tags", []):
                tag_counts[tag] = tag_counts.get(tag, 0) + 1
    
    if tag_counts:
        print(f"\nEndpoints by category:")
        for tag, count in sorted(tag_counts.items()):
            print(f"  {tag}: {count} endpoints")


def generate_postman_collection(output_path: str = "arenalab.postman_collection.json"):
    """Generate Postman collection from OpenAPI schema."""
    openapi_schema = app.openapi()
    
    # Basic Postman collection structure
    postman_collection = {
        "info": {
            "name": openapi_schema.get("info", {}).get("title", "ArenaLab API"),
            "description": openapi_schema.get("info", {}).get("description", ""),
            "version": openapi_schema.get("info", {}).get("version", "1.0.0"),
            "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"
        },
        "item": [],
        "auth": {
            "type": "bearer",
            "bearer": [
                {
                    "key": "token", 
                    "value": "{{auth_token}}",
                    "type": "string"
                }
            ]
        },
        "variable": [
            {
                "key": "base_url",
                "value": "http://localhost:8000",
                "type": "string"
            },
            {
                "key": "auth_token",
                "value": "",
                "type": "string"
            }
        ]
    }
    
    # Convert paths to Postman requests
    servers = openapi_schema.get("servers", [{"url": "http://localhost:8000"}])
    base_url = servers[0].get("url", "http://localhost:8000")
    
    paths = openapi_schema.get("paths", {})
    for path, methods in paths.items():
        for method, details in methods.items():
            request_item = {
                "name": details.get("summary", f"{method.upper()} {path}"),
                "request": {
                    "method": method.upper(),
                    "header": [
                        {
                            "key": "Content-Type",
                            "value": "application/json",
                            "type": "text"
                        }
                    ],
                    "url": {
                        "raw": f"{{{{base_url}}}}{path}",
                        "host": ["{{base_url}}"],
                        "path": path.strip("/").split("/") if path.strip("/") else []
                    },
                    "description": details.get("description", "")
                }
            }
            
            # Add request body if present
            request_body = details.get("requestBody")
            if request_body and method.upper() in ["POST", "PUT", "PATCH"]:
                content = request_body.get("content", {})
                if "application/json" in content:
                    schema = content["application/json"].get("schema", {})
                    example = schema.get("example", {})
                    if example:
                        request_item["request"]["body"] = {
                            "mode": "raw",
                            "raw": json.dumps(example, indent=2),
                            "options": {
                                "raw": {
                                    "language": "json"
                                }
                            }
                        }
            
            postman_collection["item"].append(request_item)
    
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(postman_collection, f, indent=2, ensure_ascii=False)
    
    print(f"Postman collection generated: {output_path}")


def main():
    """Main documentation generator."""
    parser = argparse.ArgumentParser(
        description="Generate API documentation for ArenaLab",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python generate_docs.py --json --yaml        # Generate both JSON and YAML
  python generate_docs.py --postman            # Generate Postman collection
  python generate_docs.py --summary            # Print API summary
  python generate_docs.py --all                # Generate all formats
        """
    )
    
    parser.add_argument("--json", action="store_true", help="Generate OpenAPI JSON")
    parser.add_argument("--yaml", action="store_true", help="Generate OpenAPI YAML")
    parser.add_argument("--postman", action="store_true", help="Generate Postman collection")
    parser.add_argument("--summary", action="store_true", help="Print API summary")
    parser.add_argument("--all", action="store_true", help="Generate all formats")
    parser.add_argument("--output-dir", default="docs", help="Output directory for documentation")
    
    args = parser.parse_args()
    
    # Create output directory
    output_dir = Path(args.output_dir)
    output_dir.mkdir(exist_ok=True)
    
    if args.all:
        args.json = args.yaml = args.postman = args.summary = True
    
    # If no specific format requested, show summary
    if not any([args.json, args.yaml, args.postman, args.summary]):
        args.summary = True
    
    if args.json:
        generate_openapi_json(str(output_dir / "openapi.json"))
    
    if args.yaml:
        generate_openapi_yaml(str(output_dir / "openapi.yaml"))
    
    if args.postman:
        generate_postman_collection(str(output_dir / "arenalab.postman_collection.json"))
    
    if args.summary:
        print_api_summary()
    
    print(f"\n📚 Documentation generated in: {output_dir.absolute()}")
    print("🌐 To view interactive docs, start the server and visit:")
    print("   http://localhost:8000/docs (Swagger UI)")
    print("   http://localhost:8000/redoc (ReDoc)")


if __name__ == "__main__":
    main()