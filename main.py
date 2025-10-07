from libs.utils import * 


if __name__ == '__main__':
    convert_json_to_file(
        input_path="output/result_gpt-4.1-mini_1759820831011.396.json",
        output_path=f"export/result_gpt-4.1-mini_1759820831011.396.xlsx",
        field_mapping={
            "input_id": "sku",
            "shopify_title": "shopify_title",
            # "ebay_title": "ebay_new_title",
            "shopify_description": "shopify_description",
            "ebay_description_html": "ebay_new_description",
            "ebay_en_description_html": "EN_ebay_new_description"
        },
        file_format="xlsx"
    ) 

