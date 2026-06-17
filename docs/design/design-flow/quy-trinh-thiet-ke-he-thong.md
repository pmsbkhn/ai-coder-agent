# Quy trình Phân tích & Thiết kế Hệ thống Mức cao

Mỗi bước được đóng gói với ba tham số — **Input (Đầu vào)**, **Action (Hành động)**, **Output (Kết quả)** — để đảm bảo tính thực thi và khả năng truy vết: Output của bước trước là Input trực tiếp của bước sau.

> **Lưu ý về tính lặp:** Quy trình trình bày tuyến tính để dễ đọc, nhưng trên thực tế **không phải waterfall**. Ranh giới hệ thống là *kết quả tinh chỉnh qua nhiều vòng*. Khi Bước 3 lộ ra một Aggregate bị chia cắt sai, phải quay lại Bước 2. Khi tích hợp ở Bước 5 trở nên phức tạp bất thường (quá nhiều lời gọi đồng bộ chéo context, saga dài lê thê), đó thường là tín hiệu ranh giới ở Bước 3 đặt sai. Điều kiện quay lui được ghi ở cuối mỗi bước liên quan.

---

## Bước 1: Khai phá Yêu cầu (Requirement Discovery)

Chuyển ngôn ngữ của Product Owner/Business thành Use Case hệ thống, làm rõ yêu cầu ngầm định, và bắt đầu chốt các ràng buộc vận hành.

* **Input:**
    * Danh sách User Stories (US).
    * Acceptance Criteria (AC) đi kèm từng US.
    * **Ràng buộc vận hành & kinh doanh** từ phỏng vấn stakeholder, hợp đồng/SLA, quy định pháp lý (compliance, data residency).
    * **Ước lượng quy mô:** số người dùng, lưu lượng kỳ vọng, tải đỉnh (peak load).

* **Action:**
    * Nhóm các US chung mục đích nghiệp vụ thành các Use Case lớn.
    * Xác định rõ Actor (Người dùng, Admin, Hệ thống bên ngoài) cho từng Use Case.
    * Phân tích AC để rút ra NFR *ẩn trong yêu cầu chức năng*; **đối chiếu thêm với ràng buộc vận hành và ước lượng tải** để rút ra các NFR *không nằm trong AC* (throughput, SLA uptime, độ trễ, bảo mật, giới hạn tải).
    * Khởi tạo **bảng thuật ngữ nghiệp vụ (Glossary / Ubiquitous Language v0)**: ghi lại mỗi khái niệm nghiệp vụ kèm định nghĩa thống nhất với Business.

* **Output:**
    * Danh sách Use Case hoàn chỉnh (Actor + Action).
    * Bảng NFR chi tiết, ghi rõ *nguồn gốc* từng chỉ tiêu (làm mỏ neo cho mọi quyết định kiến trúc sau này).
    * Bảng thuật ngữ nghiệp vụ phiên bản đầu (sẽ được làm giàu ở Bước 2 và dùng làm tiêu chí ở Bước 3).

---

## Bước 2: Phân rã Nghiệp vụ & Lập mô hình (Domain Modeling)

Rã Use Case thành các thành phần hạt nhân bằng tư duy phân tích luồng sự kiện (Event Storming).

* **Input:**
    * Danh sách Use Case.
    * Quy tắc nghiệp vụ (Business Rules) từ Acceptance Criteria.
    * Bảng thuật ngữ nghiệp vụ v0 từ Bước 1.

* **Action:**
    * Bóc tách Use Case thành các mệnh lệnh thực thi (**Commands**).
    * Xác định kết quả trạng thái sau khi thực thi (**Domain Events**).
    * Định danh **Aggregates** — lưu ý: Aggregate là **ranh giới nhất quán giao dịch / nơi bảo vệ bất biến (invariant)**, không đơn thuần là "thực thể bị tác động". Đây là phần khó và dễ sai nhất; tiêu chí là: những dữ liệu phải thay đổi cùng nhau trong một giao dịch thì nằm chung một Aggregate.
    * Bắt **Policy / Reaction**: với mỗi Domain Event, xác định nó có *kích hoạt* Command nào khác không (`Event X → Command Y`). Đây chính là nguồn gốc trực tiếp của các luồng bất đồng bộ ở Bước 5.
    * Bắt **Read Model**: xác định các góc nhìn truy vấn mà Actor cần (màn hình, báo cáo) — quyết định API query sau này.
    * Bổ sung mọi thuật ngữ mới phát hiện vào bảng Ubiquitous Language.

* **Output:**
    * Bản đồ luồng nghiệp vụ chi tiết (Event Flow): chuỗi `Actor → Command → Aggregate → Domain Event → Policy → (Command kế tiếp)`.
    * Danh sách Read Model.
    * Bảng Ubiquitous Language đã được làm giàu.

---

## Bước 3: Thiết kế Chiến lược (Strategic Design)

Chống "Big Ball of Mud" bằng cách thiết lập các ranh giới kiến trúc.

* **Input:**
    * Bản đồ luồng nghiệp vụ (Commands, Events, Aggregates, Policies) từ Bước 2.
    * Bảng Ubiquitous Language từ Bước 1–2 (làm tiêu chí gom nhóm tường minh, không còn xuất hiện "từ trên trời").

* **Action:**
    * Gom các Aggregate gắn kết chặt về nghiệp vụ và **chia sẻ cùng một định nghĩa thuật ngữ trong Ubiquitous Language** thành một nhóm. Tín hiệu cần tách context: cùng một từ mang nghĩa khác nhau ở hai nơi (ví dụ "Khách hàng" ở Sales khác "Khách hàng" ở Billing).
    * Kẻ ranh giới cô lập từng nhóm → **Bounded Contexts**.
    * Xác định **quan hệ tích hợp** giữa các Bounded Context, ghi rõ *kiểu* quan hệ chứ không chỉ Upstream/Downstream: Partnership, Customer/Supplier, Conformist, **Anti-Corruption Layer (ACL)**, Shared Kernel, **Open Host Service / Published Language**. Chính các pattern này quyết định cách tích hợp ở Bước 5.

* **Output:**
    * Sơ đồ ranh giới ngữ cảnh (**Context Map**) có gắn nhãn kiểu quan hệ trên từng đường nối.
    * Mỗi Bounded Context là ứng viên cho một Microservice hoặc Module độc lập.

* **Điều kiện quay lui:** Nếu một Aggregate phải nằm cùng lúc trong hai context, hoặc một invariant bị cắt ngang ranh giới → quay lại Bước 2 để gộp/tách lại Aggregate trước khi đi tiếp.

---

## Bước 4: Thiết kế Phân rã & Kiến trúc Vật lý (Decomposition & Physical Architecture)

> *Đổi tên từ "Tactical Design".* Trong DDD, **Tactical Design** là các building block *bên trong* một context (Aggregate, Entity, Value Object, Repository, Domain Service) — phần đó đã làm ở Bước 2. Bước này thực chất là *quyết định phân rã triển khai và quyền sở hữu dữ liệu*, nên đặt tên cho đúng để tránh nhầm.

Chuyển ranh giới logic thành các khối kiến trúc vật lý/phần mềm.

* **Input:**
    * Context Map (kèm kiểu quan hệ) từ Bước 3.
    * Bảng NFR từ Bước 1.

* **Action:**
    * Quyết định cấu trúc triển khai dựa trên NFR: Bounded Context nào cần **scale độc lập / vòng đời release riêng / đội sở hữu riêng** → tách thành Microservice; những context còn lại có thể gom thành **Modular Monolith** để giảm chi phí vận hành.
    * Thiết kế quyền sở hữu dữ liệu: mỗi Bounded Context **sở hữu** dữ liệu của mình, không cho context khác ghi/đọc trực tiếp vào kho dữ liệu nội bộ.
        * **Database per Service** là *mặc định tốt cho microservice* nhưng có đánh đổi (vận hành nhiều DB, không join chéo, cần đồng bộ dữ liệu). Nêu nó như một default có chủ đích, không phải luật bất biến.
        * Với **Modular Monolith**, mức cô lập **schema-per-module** trong cùng một database thường là đủ.

* **Output:**
    * Sơ đồ Khối Kiến trúc Mức cao (High-Level Architecture Diagram): các Services/Modules và Logical Databases tương ứng.
    * Ghi chú quyết định (decision log) cho mỗi lựa chọn microservice vs module, có dẫn chiếu NFR làm lý do.

---

## Bước 5: Thiết kế Giao tiếp & API (Integration Design)

Thiết lập "đường cao tốc" và "trạm thu phí" để các khối kiến trúc nói chuyện an toàn, tối ưu, và **nhất quán dù phân tán**.

* **Input:**
    * Sơ đồ Khối Kiến trúc từ Bước 4.
    * Luồng Domain Events + Policies + kiểu quan hệ context từ Bước 2–3.
    * NFR về độ trễ/throughput từ Bước 1.

* **Action:**
    * Chọn **đồng bộ (Sync)** hay **bất đồng bộ (Async)** không cảm tính, mà neo vào hai thứ:
        * *Kiểu quan hệ context (Bước 3):* quan hệ Customer/Supplier cần dữ liệu tức thời thường dùng sync; quan hệ qua Policy/Event thường dùng async.
        * *NFR độ trễ (Bước 1):* tác vụ nằm trong ngân sách độ trễ của người dùng → cân nhắc sync; tác vụ dài/đối soát/giảm tải → async.
    * Thiết kế hợp đồng **Sync**: REST/gRPC API contracts (cho tác vụ cần dữ liệu ngay). Tại biên với context Upstream khó kiểm soát, áp **ACL** đã định ở Bước 3.
    * Thiết kế luồng **Async**: định dạng Message/Event qua Kafka/RabbitMQ, bám theo các Policy `Event → Command` đã bắt ở Bước 2.
    * **Chiến lược nhất quán phân tán:** vì Bước 4 đã "DB per service", mọi giao dịch nghiệp vụ trải nhiều service phải dùng **Saga / Process Manager** với bước **bù trừ (compensation)** thay cho transaction phân tán. Xác định rõ orchestration hay choreography cho từng luồng.
    * Quy định chuẩn đặt tên, quản lý version (v1, v2), và cơ chế xử lý lỗi tầng truyền tin: **Retry, Dead Letter Queue, idempotency**.

* **Output:**
    * Tài liệu API Specifications (sync) + Event/Message schema (async).
    * Sơ đồ luồng giao tiếp hệ thống (System Sequence / Topology Diagram).
    * Đặc tả các Saga: các bước, sự kiện kích hoạt, và hành động bù trừ tương ứng.

* **Điều kiện quay lui:** Nếu một nghiệp vụ cần saga quá dài hoặc quá nhiều lời gọi sync chéo context để hoàn tất → ranh giới ở Bước 3 có thể đặt sai; cân nhắc gộp lại các context bị "dính" nhau.

---

# Phụ lục A: Bộ Template Artifact

**Nguyên tắc xuyên suốt:** mỗi artifact có một **ID** (tiền tố cố định) và một trường **Truy vết** trỏ về ID nguồn ở bước trước. Đây là sợi chỉ giữ format nhất quán — điền theo mẫu, không nghĩ ra cấu trúc mới.

Bảng tiền tố ID:

| Artifact | Tiền tố | Bước |
|---|---|---|
| User Story | `US-` | 1 |
| Use Case | `UC-` | 1 |
| NFR | `NFR-` | 1 |
| Thuật ngữ | `GL-` | 1–2 |
| Command / Event / Aggregate / Policy / Read Model | `CMD- / EVT- / AGG- / POL- / RM-` | 2 |
| Bounded Context / Quan hệ | `BC- / REL-` | 3 |
| Quyết định kiến trúc (ADR) | `ADR-` | 4 |
| API / Event schema / Saga | `API- / EVS- / SAGA-` | 5 |

---

## A1. User Story (US)

```
ID:          US-XXX
Tiêu đề:     <tên ngắn>
Mô tả:       Là một <Actor>, tôi muốn <mục tiêu>, để <giá trị nghiệp vụ>.
Độ ưu tiên:  Cao / Trung bình / Thấp
Acceptance Criteria (Gherkin):
  - AC-1: Given <bối cảnh>, When <hành động>, Then <kết quả mong đợi>.
  - AC-2: ...
Gợi ý NFR:   <ràng buộc ẩn nếu thấy, ví dụ "phản hồi < 2s">
Truy vết:    → thuộc Use Case UC-XX
```

---

## A2. Use Case (UC)

```
ID:              UC-XX
Tên:             <động từ + đối tượng, ví dụ "Đặt đơn hàng">
Actor chính:     <người dùng / hệ thống khởi xướng>
Actor phụ:       <hệ thống ngoài tham gia, nếu có>
Tiền điều kiện:  <trạng thái cần có trước khi bắt đầu>
Hậu điều kiện:   <trạng thái sau khi thành công>
Luồng chính:
  1. <bước>
  2. <bước>
Luồng thay thế / ngoại lệ:
  A1. <điều kiện rẽ nhánh> → <xử lý>
Truy vết:        ← gom từ US-XXX, US-YYY ; → ràng buộc NFR-XX
```

---

## A3. NFR (bảng)

Cột **Loại** dùng từ vựng **ISO 25010** để khỏi tự đặt phân loại: *Performance efficiency, Reliability (Availability), Security, Scalability, Maintainability, Compatibility, Usability, Portability*.

| ID | Loại (ISO 25010) | Chỉ tiêu đo được | Cách đo / Metric | Nguồn | Phạm vi ảnh hưởng |
|---|---|---|---|---|---|
| NFR-01 | Performance | p95 latency < 300ms | đo tại API gateway | US-012 | UC-03, BC-Order |
| NFR-02 | Availability | uptime ≥ 99.9%/tháng | giám sát uptime | Hợp đồng SLA | toàn hệ thống |
| NFR-03 | Security | mã hoá PII khi lưu | rà soát schema | Compliance | BC-Customer |

> Quy tắc: NFR phải **đo được** (có con số + cách đo) và **có nguồn**. Nếu không đo được thì chưa phải NFR, mới là mong muốn.

---

## A4. Bảng thuật ngữ nghiệp vụ (Ubiquitous Language)

| ID | Thuật ngữ | Định nghĩa thống nhất | Bounded Context | Bí danh cần tránh | Ví dụ |
|---|---|---|---|---|---|
| GL-01 | Đơn hàng | Yêu cầu mua đã được khách xác nhận, chưa thanh toán | Order | "giỏ hàng", "phiếu" | ... |
| GL-02 | Khách hàng | Hồ sơ định danh để giao hàng | Order | — | ... |
| GL-03 | Khách hàng | Đối tượng có công nợ để xuất hoá đơn | Billing | — | ... |

> Cột **Bounded Context** là bắt buộc: cùng một từ ("Khách hàng") có thể mang nghĩa khác nhau ở hai context (GL-02 vs GL-03) — đó chính là tín hiệu tách ranh giới ở Bước 3.

---

## A5. Output Bước 2 — Domain Model / Event Flow

Mỗi luồng nghiệp vụ ghi bằng một dòng notation, rồi điền chi tiết từng phần tử vào các bảng dưới.

**Notation luồng:** `Actor → CMD-x → AGG-y → EVT-z → POL-w → CMD-tiếp`

**Commands**

| ID | Tên (mệnh lệnh) | Actor | Aggregate đích | Dữ liệu vào | Tiền điều kiện / invariant |
|---|---|---|---|---|---|
| CMD-01 | Đặt đơn hàng | Khách | AGG-Order | sản phẩm, số lượng | còn hàng |

**Domain Events**

| ID | Tên (quá khứ) | Phát từ Aggregate | Dữ liệu mang theo |
|---|---|---|---|
| EVT-01 | Đơn hàng đã được tạo | AGG-Order | orderId, items, total |

**Aggregates**

| ID | Tên | Invariant cần bảo vệ | Dữ liệu thuộc về |
|---|---|---|---|
| AGG-Order | Đơn hàng | tổng tiền = Σ dòng; không sửa khi đã thanh toán | items, status, total |

**Policies (nguồn của luồng async ở Bước 5)**

| ID | Quy tắc | Truy vết |
|---|---|---|
| POL-01 | When EVT-01 (Đơn tạo) then CMD-Trừ tồn kho | → tạo luồng async ở Bước 5 |

**Read Models**

| ID | Tên | Nguồn event | Phục vụ truy vấn / màn hình |
|---|---|---|---|
| RM-01 | Lịch sử đơn hàng | EVT-01, EVT-... | màn hình "Đơn của tôi" |

---

## A6. Output Bước 3 — Context Map

**Danh mục Bounded Context**

| ID | Tên | Trách nhiệm | Aggregates bên trong | Ứng viên Service? |
|---|---|---|---|---|
| BC-Order | Quản lý đơn | tạo & theo dõi đơn | AGG-Order | Có |
| BC-Billing | Hoá đơn & công nợ | xuất hoá đơn | AGG-Invoice | Có |

**Quan hệ giữa các Context** — cột **Kiểu** dùng từ vựng DDD cố định: *Partnership, Customer/Supplier, Conformist, Anti-Corruption Layer (ACL), Shared Kernel, Open Host Service / Published Language (OHS-PL)*.

| ID | Upstream | Downstream | Kiểu | Cơ chế tích hợp | Ghi chú |
|---|---|---|---|---|---|
| REL-01 | BC-Order | BC-Billing | Customer/Supplier | async (event) | qua EVT-01 |
| REL-02 | Hệ thống ngoài | BC-Order | ACL | sync (REST) | cách ly model ngoài |

---

## A7. Sơ đồ thiết kế AD (cấu trúc theo ISO/IEC/IEEE 42010, ký hiệu C4)

Tài liệu Architecture Description gồm 5 phần theo 42010, mỗi View vẽ bằng C4 ở mức tương ứng.

```
1. STAKEHOLDERS & CONCERNS
   | Stakeholder        | Concern (mối quan tâm)                  |
   | Product Owner      | đáp ứng đúng Use Case                   |
   | Đội vận hành       | khả năng scale, uptime (NFR-02)         |
   | Bảo mật            | bảo vệ PII (NFR-03)                      |

2. VIEWPOINTS → VIEWS (mỗi view trả lời concern nào)
   | View                  | Ký hiệu        | Trả lời concern        |
   | Context View          | C4 Level 1     | phạm vi & actor ngoài  |
   | Container View        | C4 Level 2     | services + logical DB  |
   | Data Ownership View   | bảng/sơ đồ     | DB-per-service (Bước 4)|
   | Integration View      | topology       | sync/async (Bước 5)    |

3. CÁC VIEW (đính kèm sơ đồ C4 tương ứng cho từng view ở mục 2)

4. CORRESPONDENCE / TRACEABILITY
   - mỗi Container ⇄ một BC-xx (Bước 3)
   - mỗi quyết định tách service ⇄ một ADR-xx (Bước 4)

5. ARCHITECTURE DECISIONS (ADR) — mỗi quyết định một thẻ:
   ADR-XX | Bối cảnh | Quyết định | Phương án bị loại | Đánh đổi | NFR liên quan
```

> Vì sao 42010 hợp lý ở đây: nó ép bạn nối **sơ đồ ↔ concern ↔ stakeholder ↔ NFR**, đúng thứ một bản thiết kế mức cao cần để bảo vệ trước hội đồng. Nhưng nó là chuẩn *meta*, nên phần "hình vẽ" phải mượn **C4** (hoặc dùng nguyên template **arc42** nếu muốn lấy sẵn).

---

## A8. Output Bước 5 — Integration Design

### A8.1 API đồng bộ — dùng chuẩn **OpenAPI 3.x** (đây là phần tóm tắt mỗi endpoint; spec đầy đủ viết bằng OpenAPI)

```
ID:           API-XX
Owner BC:     BC-Order
Method+Path:  POST /v1/orders
Mô tả:        tạo đơn hàng mới
Request:      { items: [...], customerId }
Response:     201 { orderId } | 4xx { error } | 5xx
Auth:         Bearer token
Idempotency:  Idempotency-Key header (bắt buộc cho POST)
Lỗi:          mã lỗi chuẩn + thông điệp
Truy vết:     ← CMD-01 ; phục vụ UC-03
```

### A8.2 Event/Message bất đồng bộ — phong bì theo **CloudEvents**

```
ID:           EVS-XX
Tên event:    order.created.v1
Producer BC:  BC-Order
Consumers:    BC-Billing, BC-Inventory
Kênh:         topic "orders" (Kafka)
Khóa phân vùng: orderId
Schema (payload): { orderId, items, total, occurredAt }
Versioning:   hậu tố .vN, tương thích ngược
Độ tin cậy:   Retry n lần → Dead Letter Queue ; consumer idempotent
Truy vết:     ← EVT-01, POL-01 ; thực thi REL-01
```

### A8.3 Saga / Process Manager (nhất quán phân tán)

```
ID:        SAGA-XX
Tên:       Hoàn tất đơn hàng
Trigger:   EVS-order.created.v1
Kiểu:      Orchestration | Choreography
Timeout:   <ngân sách thời gian tổng>
Các bước:
  | # | Service     | Hành động       | Sự kiện thành công   | Hành động bù trừ        |
  | 1 | Inventory   | Trừ tồn kho     | stock.reserved       | Hoàn tồn kho            |
  | 2 | Billing     | Tạo hoá đơn     | invoice.created      | Huỷ hoá đơn             |
  | 3 | Payment     | Thu tiền        | payment.captured     | Hoàn tiền               |
Truy vết:  ← REL-01, POL-01
```
