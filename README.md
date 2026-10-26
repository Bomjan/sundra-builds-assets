# Sundra Builds Assets

Public image assets for the **Sundra Builds** Facebook page.

## Folders
- `posts/` — generated daily social graphics.
- `branding/` — brand identity assets.
- `templates/` — reusable social graphic templates.

## Publishing workflow
1. Generate a high-quality, human-designed graphic consistent with the page's visual identity.
2. Save as a PNG or JPEG to `posts/YYYY-MM-DD-topic.png`.
3. Commit the image to `main`.
4. Supply its public HTTPS raw GitHub URL to Upload-Post's `upload_photos` action, along with a caption and Facebook Page ID.
5. Verify publishing status before reporting success.

Example URL pattern:

`https://raw.githubusercontent.com/Bomjan/sundra-builds-assets/main/posts/YYYY-MM-DD-topic.png`

Only publicly shareable graphics belong in this repository. Avoid credentials, private photographs, and unpublished sensitive content.
