# Trace case: từ trace tới quyết định sai đầu tiên

Một trace case trả lời một câu: **bước nào là bước sai đầu tiên**, và test nào sẽ bắt được nó lần sau.

```bash
cd src
python -m lab9.trace_case --shape seeded_regression --claim C-002 --seed 11
python -m lab9.trace_case --shape fixed --claim C-002 --seed 11   # đối chứng
```

## Case: `seeded_regression` C-002@11

Output (rút gọn):
```
== seeded_regression C-002@11  lab8 grader: FAIL (status resolved != denied)
   1 handoff            {"request_id": "REQ-C-002", "task": "check_applicable_policy", ...}
   2 investigator       {"lookup_order": {"visible": true, "order": {"order_id": "O-202", "delay_days": 2, ...}}}
   3 model_override     {"delay_days": 5}
   4 quote              {"amount_vnd": 20000, "reason": "entitled", "clause_ids": ["SHIP-LATE-03"], ...}
   5 refund_history     {"refund_count": 0, "refunded_vnd": 0}
   6 reply              {"text": "Dạ, LogiX đã hoàn 20.000đ cho đơn O-202."}
-- ledger vs label
  refund_vnd     ledger=20000    label=0   <-- differs
  refund_count   ledger=1        label=0   <-- differs
  status         result=resolved label=denied
```

| Trường | Nội dung |
|---|---|
| Trial | `seeded_regression C-002@11`, report `E-seeded_regression-20261117-5ba1` (`src/reports/eval_seeded_regression.json`, item E-002) |
| Triệu chứng | Ledger ghi 20.000đ cho C-002, nhãn là `denied` / 0đ. `pass_rate` (status resolved ≠ denied), `refund_amount_correct` (20.000 ≠ 0) và `db_fact_kept` (có 1 event override) cùng fail. Reply nói "đã hoàn 20.000đ", khớp ledger nên `reply_matches_ledger` không fail: reply sai theo nhãn chứ không sai so với ledger. |
| Bước sai đầu tiên | **ev 3 `model_override`** `{"delay_days": 5}`: số ngày trễ 5 lấy từ ticket ("Đơn giao trễ 5 ngày") đè lên `delay_days = 2` trong DB. |
| Vì sao là bước *đầu tiên* | ev 1 `handoff` đúng claim, đúng tool chỉ đọc. ev 2 `investigator` đọc đúng đơn O-202 với `delay_days: 2` và quote của investigator là 0 (`no_entitlement`). Mọi thứ sau ev 3 chỉ là hệ quả: ev 4 tính lại quote theo 5 ngày (20.000), host ghi đúng số được đề xuất. |
| Failure mode | **FM-03** ticket_trust (layer model/prompt) |
| Đối chứng | `fixed` C-002@11: ev 1 handoff, ev 2 investigator (`delay_days: 2`), **không có `model_override`**, ev 3 quote `{"amount_vnd": 0, "reason": "no_entitlement"}`, ev 4 reply "chưa đủ điều kiện hoàn". Ledger 0, status `denied`, grader Lab 8 PASS. Cùng lỗi xuất hiện ở `swarm` C-002@55 (điểm yếu seed % 5 == 0 của swarm tham chiếu): baseline có 1/70 trial fail vì đúng bước này. |
| Regression test | `src/tests/test_lab9_trace_case.py`: `test_lab9_trace_case_seeded_regression_c002_is_caught` kiểm event thứ 3 là `model_override {"delay_days": 5}`, `DbFactKept` và `RefundAmountCorrect` trả False, grader Lab 8 FAIL. `test_lab9_trace_case_fixed_c002_passes` kiểm cùng claim@seed trên `fixed`: không override, cả hai grader True, Lab 8 PASS. Đã chạy: test đầu bắt được lỗi trên variant lỗi, test sau pass trên `fixed`. Item E-002 trong eval set có `provenance.from_trace = "seeded_regression C-002@11 (also swarm C-002@55)"`. |
| Chưa chắc chắn | Trace chỉ ghi kết quả của quyết định (`model_override`), không ghi *vì sao* agent tin ticket: với MockLLM đó là công tắc `ticket_trust`; với LLM thật có thể là prompt, hoặc parse sai số ngày. Trace cũng không ghi lời gọi `issue_refund` của host, nên việc host chấp nhận 20.000đ được suy ra từ ledger chứ không thấy trực tiếp trong trace. |

## Quy tắc

- Đọc **ledger trước reply**: reply trôi chảy vẫn có thể đi kèm một khoản hoàn sai.
- "Bước sai đầu tiên" phải dẫn số event cụ thể, không phải "agent bị nhầm".
- Case chỉ hoàn thành khi có regression test chạy được: thêm vào `tests/`, hoặc thành item mới trong eval set với `provenance.from_trace`.
