# 웹 UI 데모 데이터

웹 앱에서 폴더 선택 시 `samples/web-demo` 폴더를 선택한다.

## 포함 파일

- `sales_2024_01.csv`, `sales_2024_02.csv`: 같은 15개 컬럼 구조, 각 1,500행. 병합 그룹을 확인한다.
- `customers.csv`: 다른 9개 컬럼 구조, 1,000행. 별도 그룹을 확인한다.
- `readme.txt`: 표가 아닌 텍스트를 건너뛰는지 확인한다.

매출 데이터에는 수치형·범주형 컬럼, 군집, 희소 그룹, 결측치와 이상치가 포함된다. 전체 폴더를
업로드하면 그룹 판별, 컬럼 선택, 축소 실행, 결과 점수와 그래프 영역, 축소 CSV 다운로드를 순서대로
확인할 수 있다.

## 다시 생성하기

```powershell
backend\.venv\Scripts\python.exe scripts\make_sample_data.py --rows 3000 --files 2 --out samples\web-demo --seed 7
```

생성 데이터는 고정 seed를 사용하며 실제 개인정보나 운영 데이터를 포함하지 않는다.
