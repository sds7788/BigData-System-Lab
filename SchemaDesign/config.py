import os


class Config:

    def __init__(self):
        self.input_file = "data.jsonl"

        self.output_dir = "output"

        self.min_text_length = 50
        self.max_text_for_index = 5000
        self.year_pattern = r'\b(19|20)\d{2}\b'

        os.makedirs(self.output_dir, exist_ok=True)