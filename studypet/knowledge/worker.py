"""Run parsers in a disposable process, with a parent-enforced timeout."""
import json
import sys
from .extract import ExtractionError, extract_file


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    try:
        result = extract_file(sys.argv[1])
    except ExtractionError as error:
        result = {'error':str(error)}
    except Exception:
        result = {'error':'提取未完成，可以手动补充文字'}
    print(json.dumps(result,ensure_ascii=False))


if __name__ == '__main__':
    main()
