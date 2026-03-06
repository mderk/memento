# Delete Obsolete Files

You are removing obsolete Memory Bank files that no longer exist in the plugin.

## Obsolete Files

```json
{{variables.pre_update.obsolete_files}}
```

## Instructions

1. For each obsolete file, delete it from the project
2. Report which files were deleted

## Rules

- Only delete files listed in the obsolete_files array
- Do not delete files that are not in the list
- Report any files that could not be found (already deleted)
