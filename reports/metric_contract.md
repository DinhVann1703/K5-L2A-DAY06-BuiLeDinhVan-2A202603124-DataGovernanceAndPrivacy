# Metric contract (khai báo bắt buộc — chốt ở phút 30, trước khi chạy eval)

> Các metric chuẩn đã được cài trong `src/metrics/tracks.py`. File này là nơi nhóm **cam kết** cách dùng chúng.
> Không đổi testset, threshold hay trọng số sau khi đã thấy kết quả eval.

| Mục | Khai báo của nhóm |
|---|---|
| Track | T02 |
| Primary metric (tên đúng như evaluator in ra) | Defect Recall@B |
| Tăng tốt hay giảm tốt? | higher |
| Đơn vị đánh giá (image / region / pair / release / batch / case …) | image |
| Công thức + numerator / denominator | Số ảnh lỗi ground truth trong top 20 ảnh eval / tổng số ảnh lỗi ground truth trong split eval |
| Cách ghép prediction ↔ GT (IoU? id? tolerance?) | Ghép chính xác bằng `image_id`; evaluator lọc ảnh thuộc `split=eval`, xếp score giảm dần rồi lấy top 20 |
| Candidate pool cố định | `fixtures/t02_raw_qc/images.csv` — tổng 96 ảnh |
| Review budget B / K | B = 20 |
| Seed | 42 |
| Threshold policy (chọn trên dev như thế nào) | Score là trung bình đều của 3 percentile risk: sharpness thấp so với dev cùng camera_id; frac_dark và frac_saturated cao so với dev cùng light. Nếu nhóm dev có dưới 5 ảnh thì dùng toàn bộ dev làm mốc. Xếp score giảm dần, review top 20; không dùng GT/eval để chọn trọng số. |
| Eval split (không dùng để tune) | `eval` — 40 ảnh, chỉ dùng để chấm; không tune |
| Chỉ số lỗi xấu (miss / false alarm / false reject) | Miss = ảnh lỗi không lọt top 20; false alarm = ảnh sạch lọt top 20 |
| Slices sẽ báo cáo (≥2) | `light` (day/dusk/night), `defect_type`; xem thêm `camera_id` để phân tích cam_A/cam_B |
| Cách báo độ bất định khi N nhỏ (Wilson CI / bootstrap) | Wilson 95% CI cho Recall@B, Precision@B và false-alarm rate theo slice |
| Ngày giờ chốt + người chốt | 2026-11-14, 20:39 (+07:00); Bùi Lê Đình Văn |

Nếu baseline = 0 thì ghi rõ "baseline = 0" thay vì phần trăm cải thiện.
