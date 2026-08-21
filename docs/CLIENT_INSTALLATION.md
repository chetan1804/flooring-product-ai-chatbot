# Client website installation

The client website integrates only JavaScript. It never receives Python code, database
credentials, or the OpenAI API key.

## Before installation

The chatbot operator must register:

- the exact `site_code`;
- the storefront HTTPS origin and any approved `www` variant;
- the domain used for SKU search links;
- the default widget title and floating position.

The operator then supplies the hosted widget URL and site code.

The operator can also configure brand colors, launcher text, welcome copy, an optional logo,
and calculator defaults in the server-side site registry. These settings are returned by
the widget configuration endpoint; clients should not copy theme values into JavaScript.

## Floating installation

Place this before the closing `</body>` tag. Loading is asynchronous and does not require
React, jQuery, or another framework.

```html
<script
  async
  src="https://chatbot.example.com/widget.js"
  data-site="CLIENT001">
</script>
```

Override the registered position when needed:

```html
<script
  async
  src="https://chatbot.example.com/widget.js"
  data-site="CLIENT001"
  data-position="bottom-left">
</script>
```

## Inline installation

```html
<div id="flooring-chatbot"></div>
<script
  async
  src="https://chatbot.example.com/widget.js"
  data-site="CLIENT001"
  data-target="#flooring-chatbot">
</script>
```

For WordPress, add the snippet through an approved theme/template or script-management
mechanism. For Shopify or Magento, add it to the appropriate global theme layout. For
React/PHP/static sites, place it in the shared page shell. Load the script once per page.

## Content Security Policy

If the client has CSP, allow the chatbot origin in `script-src` and `connect-src`, and allow
catalog image hosts in `img-src`. Keep the policy as narrow as the actual deployment.

## Verification

1. Open a page from an allowed registered origin.
2. Confirm the launcher or target-element widget appears.
3. Start a session and send a flooring request.
4. Confirm recommendation cards show catalog facts and missing prices say unavailable.
5. Confirm every product link targets the registered storefront as `/?s=ENCODED_SKU`.
6. Test mobile layout, keyboard submission, loading errors, and both approved origins.
7. Verify the configured logo, colors, launcher text, calculator waste default, carton
   rounding, and material-cost disclaimer.

An `Unknown site` or `Origin not allowed` response means the operator’s registry must be
corrected; do not work around it by widening CORS to every origin.
