# save 모드: 나중에 쓸 스킬을 내 카탈로그에 보관

"이거 카탈로그에 넣어줘", "나중에 쓰게 저장해 둬", "이 스킬 찜해줘", "내 카탈로그 보여줘" 같은 요청에 쓴다. SNS나 글에서 본 스킬을 잊지 않게 모아 두는 기능이다. **설치는 하지 않는다.** 보관한 항목은 나중에 하네스를 만들 때 "내 카탈로그" 후보로 올라온다.

## 저장 절차

1. **찾기**: 사용자가 준 것으로 원 저장소를 찾는다.
   - GitHub 주소면 그대로 쓴다.
   - 이름, SNS 글, 캡처만 있으면 웹에서 찾는다. 같은 이름의 포크·사본이 여럿이면 원작자 저장소(가장 오래되고 활발한 쪽, 공식 조직)를 고르고, 확신이 없으면 후보 2~3개를 보여 주고 고르게 한다.
   - 이미 카탈로그에 있으면(`hkcatalog.py find --text <이름>`) 그 항목을 보여 주고 끝낸다.
2. **받기**: 새로 만든 빈 임시 폴더에 `git clone --depth 1 <저장소>`. 받은 코드는 실행하지 않는다.
3. **살펴보기**: `hkscan.py repo <폴더> --summary`로 스킬·훅·에이전트·상시 비용을 보고, README·LICENSE·plugin/marketplace 설정에서 설치 방법(Claude Code, Codex), 라이선스, 외부 전송을 확인한다. 라이선스가 없으면 저장은 하되 `layer: excluded`로 두고 이유를 적는다.
4. **보안 점검**: `hkinspect.py <폴더>`. 판정을 `security`에 적는다. SkillSpector가 없으면 "점검 안 됨 — 설치 전에 반드시 점검"이라고 적고 저장은 한다. 설치할 때 다시 점검한다.
5. **충돌 확인**: `hkcatalog.py find --role <역할>`과 `--text <키워드>`로 같은 일을 하는 항목을 찾고, 설명문과 지시를 비교해 기능 충돌을 `conflicts`에 적는다(`conflict-rules.md` 유형, 원문 인용). 확인할 수 없는 충돌은 적지 않는다.
6. **항목 작성**: `_workspace/harnesskit/save-<id>.json`에 카탈로그 형식으로 쓴다. 필수 필드는 `id`, `name`, `repo`, `license`, `layer`, `use_when`, `skip_when`, `install`, `detect`, `always_on`, `external_data`, `conflicts`, `verified`다. 저장소 파일을 직접 읽었으면 `verified: "direct"`로 둔다. 사용자가 말한 출처나 메모는 `memo`에 남긴다(예: "인스타에서 봄, 발표 자료 만들 때 써 보기").
   - `npx`·`uvx`·`pip` 설치 명령은 버전을 고정해 적는다.
7. **저장**: `hkcatalog.py add --file _workspace/harnesskit/save-<id>.json`. 형식 오류가 나오면 고쳐서 다시 저장한다.
8. **보고**: 한 화면으로 끝낸다.

```
보관했습니다: <이름>  (내 카탈로그 N개째)
  하는 일   <한 줄>
  쓸 때     <use_when 한 줄>
  상시 비용 <설명문 n개 · 훅 n개>
  보안 점검 <SAFE | CAUTION | DO_NOT_INSTALL | 점검 안 됨> <근거 한 줄>
  겹치는 것 <카탈로그 항목 — 유형>  (없으면 "없음")
  나중에    하네스를 만들 때 후보로 올라오고, 설치 전에 다시 점검합니다.
```

## 보기·정리

- **내 카탈로그 보기**: `hkcatalog.py mine`. 표로 이름·하는 일·보안 판정·보관한 날·메모를 보여 준다.
- **빼기**: `hkcatalog.py remove <id>`.
- **저장 위치**: `hkcatalog.py path`. 키트를 업데이트해도 지워지지 않는 곳(`~/.harnesskit/catalog.local.json`)에 있다. 팀과 나누려면 이 파일을 공유하거나, 키트 저장소의 `catalog.json`에 옮겨 넣는다.
