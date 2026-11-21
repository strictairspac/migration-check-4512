# Schema v2 — 原样谱系（父样来路）

v1 表保持不变；v2 新增以下表并给 runs 增加 lineage 快照列：

- `lineage_meta(id=1, version)`：单调递增的谱系版本号。登记与迁移落库都先对 id=1 行加行锁，保证“整批按落库时的同一版谱系认定”。
- `lineage_edges(id, child_code, parent_code, relation, version, note, created_by, registration_id, created_at)`：一条来路 = 子样—父样。`relation` 为 split（分样）或 mix（混样）；分样子样只能有一个父样，混样每条来路各存一行。`unique(child_code,parent_code)` 防止同一来路重复登记；版本号记录该来路首次登记时的谱系版本，历史不变，补录只会新增边。
- `lineage_registrations(request_id unique, actor, payload, payload_digest, status, version, response, created_at)`：补录回执。`request_id` 唯一，重试命中同一回执按原结果返回（不重复登记）；相同回执不同内容返回 409；`status=rejected` 会保留拒绝原因，重试仍以 409 回放，不会二次入库。
- `runs.lineage`：迁移成功提交时冻结的谱系快照（版本、相关边、逐行来路路径）。恢复目标行不改写它；旧备份/旧运行该列为空，追查时视作原样。

并发补录：每条登记在事务内对 `lineage_meta` 加锁后基于全部现有边做环检测；两单合起来成环时后提交的一单整单回滚并退回，另一单与无关支系照常入库。旧库启动时 `src/config/schema.py` 会幂等补列并建表。
