# Judge audit

Chạy: `python -m lab9.judge --csv <file> --audit 5` (judge replay, nhãn FAIL là lớp dương).

| Tiêu chí | n | κ | Precision | Recall | Đạt FLOORS (κ≥0.6, P≥0.8, R≥0.7)? | Quyết định |
|---|---|---|---|---|---|---|
| tone_ok | 100 | 0.757 | 0.857 | 0.800 | Đạt | **dùng** (chỉ cho tone, không cho tiền/approval) |
| helpful | 100 | 0.375 | 1.000 | 0.300 | Không (κ và R dưới sàn) | **loại** |

Ma trận nhầm lẫn:
- tone_ok: tp=24, fp=4, fn=6, tn=66. Tỉ lệ FAIL quan sát 0.28 → Rogan-Gladen hiệu chỉnh 0.30.
- helpful: tp=9, fp=0, fn=21, tn=70. Tỉ lệ FAIL quan sát 0.09 → hiệu chỉnh 0.30.

## Case audit thủ công (10 bất đồng của tone_ok)
| # | Case | Judge nói | Người nói | Ai đúng? | Ghi chú / sửa rubric |
|---|---|---|---|---|---|
| 1 | H-008 "Em đã hoàn tiền cho anh rồi nha, anh check giúp em." | PASS | FAIL | Người | Xưng "em" + "nha" quá suồng sã với khách; judge coi là thân thiện. Rubric: thêm dòng "xưng hô thương hiệu: LogiX – anh/chị". |
| 2 | H-017 "Dạ, bạn ơi LogiX đã hoàn 25.000đ ... rồi nha." | PASS | FAIL | Người | Xưng "bạn" với khách lớn tuổi; judge coi là thân thiện. Rubric: liệt kê cách xưng hô không được dùng (bạn ơi, nha, nhé) kèm ví dụ FAIL. |
| 3 | H-029 "Dạ, vui lòng chờ. ... không cần nhắn thêm." | PASS | FAIL | Người | Câu cụt, ra lệnh khách. Judge chỉ nhìn "Dạ" + "vui lòng". Rubric: chấm cả giọng điệu cả câu, có ví dụ "lịch sự bề mặt nhưng gạt khách". |
| 4 | H-042 "Dạ, đơn O-808 đã hoàn 120.000đ. Tiền về trong 3–5 ngày ạ." | FAIL | PASS | Người | Ngắn nhưng đủ ý; judge phạt vì "thiếu xin lỗi". Rubric: ghi rõ xin lỗi không bắt buộc khi yêu cầu đã được giải quyết. |
| 5 | H-051 "Dạ, LogiX đã refund 90.000đ cho đơn O-202 ạ." | FAIL | PASS | Người | CS LogiX cho phép từ "refund"; judge phạt vì tiếng Anh. Rubric: thêm danh sách thuật ngữ tiếng Anh được phép. |
| 6 | H-063 "Dạ, LogiX đã hoàn 20.000đ và sẽ hoàn thêm cho anh/chị ạ." | PASS | FAIL | Người | Hứa hẹn không có căn cứ ("sẽ hoàn thêm"). Thuộc tone vì gây kỳ vọng sai. Rubric: thêm tiêu chí "không hứa điều chưa xác nhận". |
| 7 | H-070 "Dạ, LogiX đã hoàn 90.000đ cho đơn O-909 ạ 😂😂" | PASS | FAIL | Người | Emoji cười không phù hợp. Rubric: cấm emoji trong reply hoàn tiền. |
| 8 | H-081 "Dạ, đơn O-107 chưa đủ điều kiện hoàn theo chính sách hiện hành ạ." | FAIL | PASS | **Judge** | Nhãn người sai (người chấm đọc nhầm ticket). Hành động: **sửa nhãn người** thành FAIL ở bản nhãn tiếp theo, không sửa rubric. Bất đồng không phải lúc nào cũng là lỗi của judge. |
| 9 | H-088 "Dạ, dạ, LogiX đã hoàn 40.000đ cho đơn O-233 ạ." | FAIL | PASS | Người | Lặp "Dạ" do lỗi gõ; người cho qua, judge phạt. Rubric: nêu rõ lỗi gõ nhỏ không làm FAIL tone. |
| 10 | H-094 "Da, LogiX da hoan 40.000đ cho don O-341, xin loi vi su bat tien." | PASS | FAIL | Người | Dịch máy, mất dấu tiếng Việt. Rubric: thêm "phải có dấu tiếng Việt". |

Mẫu: 6/10 bất đồng là judge bỏ sót FAIL (fn: xưng hô suồng sã, giọng ra lệnh, hứa suông, emoji, mất dấu). 4/10 là judge báo FAIL khi người nói PASS; trong đó 3 lần judge sai (đòi xin lỗi, phạt "refund", phạt lỗi gõ) và 1 lần (H-081) nhãn người sai. Sửa rubric: (1) danh sách tín hiệu FAIL cụ thể kèm ví dụ, (2) danh sách những gì *không* làm FAIL (không xin lỗi khi đã giải quyết, từ "refund", lỗi gõ nhỏ), (3) sửa nhãn H-081.

## Kết luận
- **helpful bị loại.** Recall chỉ 0.30 (fn=21, tp=9): judge bỏ sót 70% reply mà người chấm là không hữu ích. κ=0.375 dưới sàn 0.6. Precision 1.0 không cứu được: judge rất ít khi nói FAIL nên chỉ đúng khi FAIL đã quá rõ. Nguyên nhân chính nằm ở cột `human_failure`: **18/21 ca bỏ sót là "sai tiền"**, ví dụ HL-015 reply "đã hoàn 55.000đ" trong khi ledger ghi 40.000đ, HL-020 nói 90.000đ khi ledger 120.000đ, HL-016/HL-028 xin lỗi dài nhưng không nói số tiền 35.000đ đã hoàn. Judge chỉ đọc reply, không thấy ledger, nên về nguyên tắc không thể chấm tiêu chí này. 3 ca còn lại là sai xưng hô (HL-047 "Ok bạn ... nhé"), thuộc về tone. Dùng judge này làm gate thì phần lớn regression lọt qua, và tỉ lệ lỗi quan sát (0.09) thấp hơn ước tính sau hiệu chỉnh (0.30) hơn 3 lần.
- **Thay helpful bằng gì:** phần "sai tiền" chính là FM-08, chấm bằng grader code `reply_matches_ledger` (so số tiền trong reply với `refund_vnd` của ledger), blocking trong `metric_spec.yaml`. Phần xưng hô chuyển sang rubric tone.
- **tone_ok được dùng**, nhưng chỉ cho tone, không blocking trong v1, và luôn báo cả tỉ lệ đã hiệu chỉnh Rogan-Gladen.
- Tiền và approval không bao giờ chấm bằng judge: FM-08 (reply nói sai số tiền) dùng grader code `reply_matches_ledger`.
- Rủi ro còn lại: judge chỉ được kiểm trên dữ liệu replay đã công khai (100 dòng mỗi tiêu chí); sau khi sửa rubric cần nhãn người mới để có held-out thật, nếu không κ đo trên chính dữ liệu dùng để sửa rubric sẽ lạc quan.
