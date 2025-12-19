import re


def clean_text(text):
    """清洗文本数据"""
    if not text:
        return ""

    text = re.sub(r'\s+', ' ', text)

    text = re.sub(r'[^\w\s\u4e00-\u9fff，。！？；：""''()\[\]{}《》]', ' ', text)

    text = text.replace('，', ',').replace('。', '.').replace('；', ';')

    return text.strip()