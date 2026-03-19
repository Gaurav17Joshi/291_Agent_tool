from datasets import load_dataset

ds = load_dataset("princeton-nlp/SWE-bench_Lite")
ds.save_to_disk("./swe-bench-lite")

