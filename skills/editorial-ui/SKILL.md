---
name: editorial-ui
description: Search web images and render ChatGPT-style inline editorial cards (image galleries, spec cards, 4-quadrant meaning cards, and timelines) using the editorial-media MCP server.
---

# ChatGPT-Style Editorial UI & Image Cards

Use this skill whenever an explanation benefits from **visual reference images**, **spec/overview cards**, **4-quadrant cards**, or **step timelines** rendered cleanly inline.

## Workflow

1. **Search Images (per topic/section where visual references help)**:
   Call `editorial-media` -> `search_images(query="...", limit=3)`.
   This fetches thumbnails locally and returns `image_id` and `file_path` metadata.

2. **Visually Inspect Fetched Images (`read_file`) — Mandatory**:
   Before embedding any image, call `read_file` in parallel on the returned `file_path`s!
   - Actually **look at** each image to verify it directly matches the specific point being explained, has no distracting watermarks/corruption, and shows clear visual detail.
   - Select only the `image_id`(s) that genuinely add visual clarity. If none fit well after 1–2 targeted queries, **do not force a filler image**—omit `image_ids` (use text-only cards like spec/quadrant/timeline if useful) or switch to a `generative_ui` diagram instead.
   - **Ground your prose in the image**: Explicitly point to and explain specific visual elements you observed (e.g., layout, colors, labels, clothing/design details, diagram flow) in the surrounding Markdown section so the image and text work together as one explanation.

3. **Build & Interleave Multiple Editorial Widgets**:
   Call `editorial-media` -> `render_editorial_widget(...)` with:
   - `output_path`: `<Artifact Directory Path>/<unique_name>.html` (e.g., `editorial_1_overview.html`, `editorial_2_comparison.html` — always use unique filenames so you can embed multiple cards across different sections of one response)
   - `title` / `subtitle`: concise card header
   - `image_ids`: list of verified `image_id` values from Step 2
   - Optional structured blocks: `spec_card`, `quadrants` (up to 4), `timeline`

4. **Embed Inline Where Needed**:
   Place `<agent-embed src="file:///<output_path>"></agent-embed>` **directly inside each relevant section** of your response (interleaved with `generative_ui` interactive widgets wherever interactive intuition also helps), alongside thorough, high-readability long-form Markdown prose.

## Guidelines

- Keep widgets compact (`<= 450px` tall) so they do not scroll inside the chat column.
- Do not duplicate the entire prose explanation inside the widget; use the widget for **visual anchors** (images, specs, timelines, 4-quadrant summaries) and write the deep narrative, edge cases, and Q&A table in Markdown.
