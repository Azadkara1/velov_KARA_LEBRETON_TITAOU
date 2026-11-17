| variante | taille Mo | p50 ms | p95 ms | précision SST-2 | accord float32 | désaccords |
|---|---|---|---|---|---|---|
| float32 | 267.9 | 145.6 | 149.7 | 91.06% | 100.00% | 0 |
| int8 torch.ao (quantize_dynamic) | 138.7 | 44.2 | 48.4 | 90.02% | 95.76% | 37 |
| int8 torchao | 138.9 | 89.9 | 100.0 | 90.60% | 99.54% | 4 |
