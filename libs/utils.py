import pandas as  pd 
from pathlib import Path 
import json, csv
from typing import Union, List, Dict 


def convert_json_to_file(
    input_path: str,
    output_path: str,
    field_mapping: Dict[str, str],
    file_format: str = "xlsx"      
):
    input_path = Path(input_path)
    if not input_path.exists():
        raise FileNotFoundError(f"Không tìm thấy file: {input_path}")

    with open(input_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    if not isinstance(data, list):
        raise ValueError("JSON phải là list các object!")

    processed_data: List[Dict[str, str]] = []
    for item in data:
        mapped_item = {
            export_field: item.get(source_field, "")
            for source_field, export_field in field_mapping.items()
        }
        processed_data.append(mapped_item)


    df = pd.DataFrame(processed_data)

    if file_format == "csv":
        df.to_csv(output_path, index=False, encoding='utf-8-sig')
    elif file_format == "xlsx":
        df.to_excel(output_path, index=False)
    else:
        raise ValueError("Chỉ hỗ trợ file_format: csv hoặc xlsx")

    print(f"✅ Export thành công: {output_path}")

"""
convert_json_to_file(
    input_path="",
    output_path="products.xlsx",
    field_mapping={
        "sku": "sku",
        "title": "title"
    },
    file_format="xlsx"
)
"""


def convert_file_to_json(
    input_path: str,
    output_path: str = None
) -> Union[List[Dict], None]:
    path = Path(input_path) 
    if path.suffix.lower() == '.csv':
        df = pd.read_csv(path)
    elif path.suffix.lower() in ['.xlsx', '.xls']:
        df = pd.read_excel(path)
    else:
        raise ValueError("Chỉ hỗ trợ file .csv hoặc .xlsx")

    json_data = df.fillna("").to_dict(orient='records')

    if output_path:
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(json_data, f, ensure_ascii=False, indent=2)
        print(f"✅ Đã xuất JSON ra: {output_path}")
        return None
    else:
        return json_data



