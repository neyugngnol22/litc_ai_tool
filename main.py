from libs.utils import * 


if __name__ == '__main__':
    convert_json_to_file(
        input_path="output/result_gpt-4o_1757497942513.9045.json",
        output_path="export/products_4o.xlsx",
        field_mapping={
            "input_id": "sku",
            "shopify_title": "shopify_title",
            "ebay_title": "ebay_new_title",
            "shopify_description": "shopify_description",
            "ebay_description_html": "ebay_new_description"
        },
        file_format="xlsx"
    ) 

