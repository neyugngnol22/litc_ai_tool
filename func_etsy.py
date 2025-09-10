tool = [
    {
        "type": "function",
        "name": "optimize_product_data_for_etsy",
        "description": "Optimize Shopify product data into Etsy-ready format: SEO title, persuasive descriptions (short & long), tags, and Etsy-specific attributes.",
        "parameters": {
            "type": "object",
            "properties": {
                "new_product_title": {
                    "type": "string",
                    "description": """
                        Rules:
                        - ≤140 characters.
                        - High-intent keywords near the beginning.
                        - Natural, readable, and relevant to handmade/vintage items.
                        - No keyword stuffing or unverifiable brand claims.
                    """
                },
                "new_product_description": {
                    "type": "string",
                    "description": """
                        Rules:
                        - Concise (inverted pyramid style).
                        - Start with the most important info.
                        - Should feel more detailed and personal while still optimized for Etsy SEO.
                        - paragraphs with bullet points for specs and options, option values.
                        - Natural keyword use.
                        - End with an internal link suggestion.
                    """
                },
                "new_tags": {
                    "type": "array",
                    "items": { "type": "string" },
                    "description": """
                        Rules:
                        - Max 13 tags.
                        - Each tag ≤20 characters.
                        - Use keyword phrases buyers might search.
                        - Avoid repetition or plural forms already used.
                    """
                },
                "new_attributes": {
                    "type": "string",
                    "description": """
                        Etsy-specific product attributes like:
                        - Material, color, size, style, occasion, holiday, room, etc.
                        - Should align with Etsy's attribute system.
                    """
                }
            },
            "required": [
                "new_product_title",
                "new_product_description",
                "new_tags",
                "new_attributes"
            ]
        }
    }
]