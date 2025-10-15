import re


def postprocess_schema_tags(result, generator, request, public):
    """
    Postprocessing hook to tag endpoints by their app name based on URL patterns.
    """
    paths = result.get("paths", {})

    for path_name, path_item in paths.items():
        # Extract app name from URL path
        # Pattern: /v1/{app_name}/... -> extract {app_name}
        match = re.search(r"/v\d+/([^/]+)/", path_name)
        if match:
            app_name = match.group(1)
            # Capitalize the first letter for better display in docs
            tag_name = app_name.capitalize()

            # Update tags for all HTTP methods in this path
            for method in [
                "get",
                "post",
                "put",
                "patch",
                "delete",
                "options",
                "head",
                "trace",
            ]:
                if method in path_item:
                    path_item[method]["tags"] = [tag_name]

    return result
