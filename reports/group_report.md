# Individual Report — Day 06 Data Lab (Field-to-Release PoC)

> Bản làm cá nhân của Bùi Lê Đình Văn, Track T02. Bản report này chỉ ghi số đo đã có trong output script. Evaluator chính thức chưa chạy được tại máy học viên vì repo không phân phối ground truth; các ô metric được giữ ở trạng thái chờ, không tự điền số.

## 00 · Thông tin cá nhân

| Mục | Giá trị |
|---|---|
| Group ID | G06 |
| Challenge | T02 · Raw QC Triage: ảnh mờ, lóa và thiếu sáng |
| Thành viên | Bùi Lê Đình Văn — làm cá nhân; tích hợp, dữ liệu, thuật toán, QA/metric, review và report |
| Git URL | https://github.com/DinhVann1703/K5-L2A-DAY06-BuiLeDinhVan-2A202603124-DataGovernanceAndPrivacy |
| Tag demo-180m | Chưa tạo |
| Tag final-24h | Chưa tạo |
| Deadline (giờ VN) | Chưa xác nhận; theo lịch do giảng viên thông báo |

## 01 · Vấn đề

Ảnh đầu vào kém chất lượng có thể làm giảm độ tin cậy của các hệ thống thị giác máy tính ở các bước downstream. Người phụ trách dữ liệu phải tìm ảnh mờ, lóa, thiếu sáng hoặc bị nén mạnh rồi quyết định giữ lại hay yêu cầu chụp lại. Với ngân sách review cố định B=20, không thể xem thủ công toàn bộ 96 ảnh theo thứ tự bất kỳ.

Hệ thống nhận ảnh và metadata gồm image_id, path, camera_id, light và split; đầu ra là score xếp hạng ảnh nghi lỗi, hàng review 20 ảnh và hành động của reviewer KEEP hoặc RECAPTURE. Score cao hơn nghĩa là cần xem trước, không phải xác suất ảnh bị lỗi.

Policy hiện tại là HOLD cho đến khi có kết quả evaluator chính thức và xác nhận các hard slice. GO chỉ khi metric đạt tiêu chí do giảng viên/domain owner xác nhận và không còn lỗi nghiêm trọng ở các slice. REWORK nếu Recall@B thấp, false alarm cao hoặc có lỗi hệ thống theo điều kiện/camera. Bộ tài liệu học viên không đặt ngưỡng số cho GO; vì vậy không tự tuyên bố đạt.

Giả định: metadata camera/light đáng tin cậy; các synthetic corruption phản ánh được một phần lỗi QC thực tế; độ sáng thấp có thể là điều kiện chụp hợp lệ ban đêm nên không tự động đồng nghĩa với RECAPTURE. Trước khi triển khai trên dữ liệu thật cần domain owner xác nhận mức chất lượng tối thiểu và cách xử lý ảnh đêm.

## 02 · Dữ liệu và provenance

| Split | N | Nguồn / link | License | Synthetic? |
|---|---:|---|---|---|
| dev | 56 ảnh | fixtures/t02_raw_qc; sinh bởi tools/make_fixtures.py, seed 42 | CC0-1.0 theo manifest | Có |
| eval / heldout | 40 ảnh | fixtures/t02_raw_qc; cùng bộ synthetic, chia theo scene | CC0-1.0 theo manifest | Có |

Tổng candidate pool là 96 ảnh 320×180 từ 24 cảnh gốc. Schema metadata là image_id, path, camera_id, light, split. Nhãn ground truth của track gồm defect_type ∈ {none, blur, glare, dark, compression}, severity 0–2 và is_defect. Ground truth không nằm trong student repo; evaluator local báo thiếu fixtures/t02_raw_qc/gt/labels.csv và chỉ dẫn rằng giảng viên chạy official evaluation.

Split được chia theo scene/group, không chia từng ảnh độc lập; 56 ảnh dev và 40 ảnh eval. Seed là 42. Lệnh preflight trước khi làm PoC báo T02 manifest hash khớp. Manifest ghi nguồn synthetic và license CC0-1.0. Không dùng data/real, không tải ảnh thật và không đưa PII thật vào pipeline.

## 03 · Nghiên cứu và thiết kế

Các tài liệu tham khảo được dùng để định hướng đánh giá điều kiện ảnh và review:

1. [ACDC dataset — ETH Zürich](https://acdc.vision.ee.ethz.ch/overview), xem ngày 2026-11-14. ACDC tập trung vào cảnh lái xe trong điều kiện bất lợi, gồm ban đêm, đồng thời có ảnh điều kiện bình thường tương ứng. Tài liệu này nhấn mạnh cần xem xét riêng ảnh ban đêm và vùng khó quan sát thay vì loại theo một tín hiệu toàn ảnh.
2. [ISO/IEC TR 5259-6:2026 — ISO](https://www.iso.org/standard/5259-6?browse=ics), xem ngày 2026-11-14. Tài liệu mô tả việc dùng visualization để stakeholder đánh giá measures chất lượng dữ liệu; ở PoC, contact sheet giúp reviewer xem ảnh, score, lý do và ghi override. Đây là tài liệu tham khảo, không phải tuyên bố PoC tuân thủ tiêu chuẩn.
3. [Quality control — CVAT documentation](https://docs.cvat.ai/docs/qa-analytics/quality-control/), xem ngày 2026-11-14. Tài liệu cung cấp ví dụ về quy trình QA có reviewer và quality-control; PoC không dùng CVAT mà dùng công cụ offline trong repo.

Data flow:

~~~text
fixtures + manifest
    → kiểm tra provenance/hash
    → đọc ảnh và metadata
    → tính sharpness, frac_dark, frac_saturated
    → chuẩn hóa risk theo phân phối dev cùng camera/light
    → xếp hạng score, lấy top 20
    → reviewer KEEP/RECAPTURE + note
    → áp dụng pred_action và ghi audit
    → quyết định HOLD chờ official evaluation
~~~

Không dùng model pretrained hoặc network. Pipeline dùng các helper Pillow, NumPy, SciPy có sẵn trong repo: Laplacian variance và brightness_stats. PoC tính ba percentile risk: sharpness thấp so với dev cùng camera_id; frac_dark cao và frac_saturated cao so với dev cùng light. Nếu nhóm tham chiếu có dưới 5 ảnh thì dùng toàn bộ dev. Score là trung bình đều của ba risk, rồi xếp giảm dần. Đây là điểm xếp hạng, không phải xác suất và không dùng GT.

Trade-off: cách làm chạy CPU, offline, dễ giải thích và dùng dev làm mốc theo camera/light. Đổi lại, 56 ảnh dev là ít; frac_saturated toàn ảnh có thể báo động nhầm vì biển báo đỏ/điểm sáng bình thường; PoC chưa có feature blockiness riêng cho lỗi compression và chưa có ROI để đánh giá lóa cục bộ trên biển số.

## 04 · Baseline và PoC

Baseline là Laplacian toàn ảnh: sharpness = laplacian_variance(image), score = 1/(sharpness + 1e-6); xếp score giảm dần và lấy B=20. Output: out/laplacian/ranked_review.csv. Run metadata ghi 96 ảnh, seed 42, offline=true, runtime 0.3942 giây, config hash 7f9ff0c716b6 và Git SHA b0ce8bf. Bản code Laplacian được lưu ở src/pipeline_laplacian.py.

PoC kết hợp risk blur, thiếu sáng và bão hòa bằng percentile tham chiếu dev như mô tả ở Section 03. Output: out/poc/ranked_review.csv. Run metadata ghi 96 ảnh, seed 42, offline=true, runtime 0.4652 giây, 20 quyết định review đã được nạp, config hash f780496f59ba; run_info ghi Git SHA b0ce8bf là HEAD tại lúc chạy, chưa phải SHA của một commit cuối riêng cho PoC.

Baseline và PoC dùng cùng fixture, candidate pool 96, budget 20, seed 42 và split eval cố định. Evaluator local không tạo metrics_baseline.json hoặc metrics_poc.json vì không có GT. Do đó chưa có bảng compare chính thức:

| Metric | Baseline | PoC | Δ / ghi chú |
|---|---|---|---|
| Defect Recall@B (image, B=20) | Chờ evaluator chính thức | Chờ evaluator chính thức | Không suy đoán |
| Precision@B (image) | Chờ evaluator chính thức | Chờ evaluator chính thức | Không suy đoán |
| False alarm theo light / hard slice | Chờ evaluator chính thức | Chờ evaluator chính thức | Cần N và GT theo slice |
| Runtime toàn bộ 96 ảnh | 0.3942 giây từ run_info.json | 0.4652 giây từ run_info.json | Thời gian local; không thay metric eval |

Không tính phần trăm cải thiện hay kết luận PoC tốt hơn baseline khi chưa có metric GT.

## 05 · Evaluation protocol

Primary metric là Defect Recall@B, đơn vị image, higher tốt hơn:

- Numerator: số ảnh có is_defect=1 trong top 20 ảnh thuộc eval.
- Denominator: tổng số ảnh có is_defect=1 trong toàn bộ split eval.
- Precision@B = số ảnh lỗi ground truth trong top 20 / B.
- Ghép prediction với GT bằng image_id chính xác; evaluator lọc dự đoán về image_id thuộc eval, sắp score giảm dần rồi lấy top B.
- Miss: ảnh lỗi không lọt top 20. False alarm: ảnh sạch lọt top 20.
- Candidate pool cố định: 96 ảnh trong images.csv; evaluator chấm 40 ảnh eval. B=20, seed=42.
- Không có ngưỡng score phân lớp; xếp hạng top 20. Đặc trưng/trọng số PoC được chốt theo policy trong reports/metric_contract.md và không dùng eval để tune.
- Slices: light (day/dusk/night), defect_type; xem thêm camera_id (cam_A/cam_B) trong phân tích lỗi.
- Khi N nhỏ, protocol đã chọn Wilson 95% CI cho Recall@B, Precision@B và false-alarm rate theo slice.

Các lệnh evaluator dự kiến do giảng viên chạy với GT chính thức:

~~~powershell
python -m src.evaluate --track t02 --pred out/laplacian/ranked_review.csv --run-name baseline --out reports/metrics_baseline.json
python -m src.evaluate --track t02 --pred out/poc/ranked_review.csv --run-name poc --out reports/metrics_poc.json
python -m src.compare reports/metrics_baseline.json reports/metrics_poc.json --out reports/table1_baseline_vs_poc.md
~~~

Tại máy học viên, lệnh evaluate đã dừng với thông báo ground truth file not found. Không sửa tay file metrics và không tự tạo kết quả thay cho evaluator.

## 06 · Result slices và failure cases

Kết quả numeric cho light, defect_type và camera_id đang chờ official eval. Hai ví dụ kiểm tra bằng ảnh:

1. img_22_0 vào PoC queue với reason high_saturation nhưng nhìn ảnh không thấy vùng cháy sáng làm mất chi tiết hữu ích; review draft chọn KEEP. Đây là false alarm tiềm năng do điểm đỏ của biển báo có thể làm tăng saturated fraction.
2. img_18_3 là cảnh đêm mờ và được baseline xếp hạng 3 vì low_sharpness. Cảnh và vật thể vẫn nhận ra nhưng độ nét thấp; cần cân bằng chất lượng ảnh với việc giữ dữ liệu ban đêm hữu ích. Không nên loại tất cả ảnh đêm chỉ vì mean brightness thấp.
3. img_22_2 được PoC xếp hạng cao với reason high_saturation, trong khi quan sát ảnh gợi ý vỡ hạt/khối. Điều này cho thấy reason hiện tại là tín hiệu trội chứ chưa phải chẩn đoán defect type; cần feature blockiness riêng.

Latency đo cục bộ từ run_info.json: baseline 0.3942 giây/96 ảnh; PoC 0.4652 giây/96 ảnh trên cùng môi trường ghi trong run_info. Đây là runtime pipeline, không phải latency evaluator hay benchmark ngoài máy này.

## 07 · Review và quyết định

Baseline queue: out/laplacian/review_queue.csv, B=20, sắp score giảm dần. Contact sheet offline ở out/laplacian/contact_sheet.html. CSV đã ghi 20 quyết định (18 edit, 2 reject) và ghi chú quan sát; review được thực hiện với hỗ trợ AI.

PoC queue: out/poc/review_queue.csv; review evidence ở out/poc/review_queue_reviewed.csv. File có 20 quyết định (12 edit, 8 reject), trong đó các gợi ý trực quan có AI hỗ trợ; reviewer cần xác nhận nội dung trước khi nộp. Pipeline áp dụng override vào pred_action và ghi các override vào out/poc/audit_log.jsonl. Contact sheet: out/poc/contact_sheet.html.

Quy ước ghi review: edit + RECAPTURE khi reviewer yêu cầu chụp lại; reject + KEEP khi reviewer bác cảnh báo và giữ ảnh. Ghi chú giải thích quyết định; score gốc vẫn được giữ để metric ranking có thể đối chiếu.

Decision hiện tại là HOLD, reason_code=OFFICIAL_EVAL_PENDING, owner=Bùi Lê Đình Văn - reviewer. Evidence gồm out/poc/ranked_review.csv và out/poc/review_queue_reviewed.csv. HOLD cho đến khi evaluator chính thức cung cấp metric và người phụ trách xác nhận các hard slice; dùng REWORK nếu có miss/failure slice không chấp nhận được.

## 08 · Reproduce và kiểm tra

PoC run local:

~~~powershell
.\.venv\Scripts\python.exe -m src.main --config .\configs\lab.yaml --track t02 --input .\fixtures\t02_raw_qc --output .\out\poc --run-name poc --pipeline src.pipeline --offline --seed 42
~~~

Baseline output đã sinh ở out/laplacian. File run_info ghi pipeline src.pipeline, runtime 0.3942 giây và status 0. PoC run_info ghi status 0 và n_reviewed=20.

Môi trường từ run_info: Python 3.13.7; Windows 11 (10.0.26200); processor string “Intel64 Family 6 Model 141 Stepping 1, GenuineIntel”. Preflight trước thay đổi PoC báo 0 FAIL, 2 WARN; T02 fixture hash khớp. WARN là data/real và models_optional không có, đều không bắt buộc cho T02.

pytest -q đã chạy ở giai đoạn setup nhưng output cuối không được lưu; chưa chạy lại sau khi sửa pipeline. Kết quả test cuối: chờ chạy và ghi chính xác trước khi nộp. Git SHA b0ce8bf có trong run_info; commit/tag cuối cho thay đổi PoC đang chờ.

## 09 · Giới hạn và đạo đức

Dữ liệu hiện tại hoàn toàn synthetic, không có ảnh người thật hoặc PII; license ghi trong manifest là CC0-1.0 cho fixture generated. Không dùng data/real và không tuyên bố hệ thống đạt GDPR, luật Việt Nam hay tiêu chuẩn ISO.

Global sharpness có thể nhầm camera có quang học mềm; brightness thấp có thể hợp lệ ở cảnh đêm; saturated fraction có thể coi biển báo đỏ là lóa; vùng cháy sáng nhỏ trên biển số có thể bị bỏ qua; compression chưa được chấm riêng. Chỉ có 56 ảnh dev nên percentile theo nhóm có thể biến động. Scale 10× chưa benchmark; cần đo lại trước triển khai.

Kế hoạch: reviewer xác nhận PoC review draft; thêm blockiness/compression feature và glare ROI; báo cáo light/camera slices; lấy dữ liệu thật có license và provenance nếu được cấp; chờ official eval trước khi thay đổi policy.

## 10 · Đóng góp cá nhân

| Học viên | Git author/email | Module / vai trò | Commit SHA / evidence | Trình bày |
|---|---|---|---|---|
| Bùi Lê Đình Văn | DinhVann1703 <builedinhvan@gmail.com> | Cá nhân: config, baseline, thuật toán PoC, metric contract, review, report | Run metadata ghi base SHA b0ce8bf; commit chứa thay đổi cuối và tag còn chờ | Chờ xác nhận |

Có sử dụng AI hỗ trợ giải thích code và tạo draft ghi chú review; reviewer cần tự xác nhận review draft trước khi nộp. Bảng này chỉ có một học viên, không khai nhóm hoặc thành viên khác.

## 11 · Tài liệu tham khảo

| URL | Ngày xem | Ý nghĩa |
|---|---|---|
| https://acdc.vision.ee.ethz.ch/overview | 2026-11-14 | Tập trung vào điều kiện lái xe bất lợi, có ban đêm; gợi ý phân tích theo điều kiện và giữ hard negatives hữu ích. |
| https://www.iso.org/standard/5259-6?browse=ics | 2026-11-14 | Khung visualization để stakeholder đánh giá measures chất lượng dữ liệu; dùng làm bối cảnh cho contact sheet/report, không tuyên bố compliance. |
| https://docs.cvat.ai/docs/qa-analytics/quality-control/ | 2026-11-14 | Ví dụ quy trình quality control và review; PoC không triển khai CVAT. |

## Checklist nộp

- [x] Repo cá nhân và input synthetic có provenance; seed 42, offline=true.
- [x] Có baseline Laplacian, PoC, review queue, override record và decision HOLD.
- [ ] Reviewer xác nhận lại PoC AI-assisted draft.
- [ ] Chạy pytest sau thay đổi và lưu đúng output.
- [ ] Giảng viên chạy official evaluation; nhận metrics_baseline.json, metrics_poc.json và table1_baseline_vs_poc.md.
- [ ] Commit các thay đổi cuối, tạo tag demo-180m/final-24h và cập nhật SHA/deadline.
