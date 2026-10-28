# Устройство IPC-2581 (по экспорту Altium, ревизия B)

Пространство имён: `http://webstds.ipc.org/2581` (у всех элементов — в xpath `{ns}Tag`). Корень `IPC-2581@revision`.
Структура ниже снята скриптом `ipc2581_inspect.py tags` на реальной плате; числа — оттуда же (107 компонентов).

## Верхний уровень

```
IPC-2581
├─ Content                        перечень содержимого
│   ├─ FunctionMode, StepRef, LayerRef×N, BomRef
│   ├─ DictionaryStandard@units   СЛОВАРЬ СТАНДАРТНЫХ ПРИМИТИВОВ (форма площадок): EntryStandard@id
│   │     └─ Circle@diameter | RectCenter@width,height | Contour/Polygon  (RoundRect, Oval и др. — в других САПР)
│   └─ DictionaryColor            цвета слоёв (для отображения)
├─ LogisticHeader                 роли, компания, автор
├─ Bom/BomHeader, BomItem×N       спецификация (BomItem → RefDes×M)
└─ Ecad
    ├─ CadHeader@units            ЕДИНИЦЫ всего файла; Spec×N — материалы слоёв (Property@text: Copper, FR-4…)
    └─ CadData
        ├─ Layer×N                name, layerFunction, side, polarity
        ├─ Stackup/StackupGroup/StackupLayer   sequence, thickness, SpecRef
        └─ Step@name               «плата» (у панели — несколько Step)
            ├─ Datum@x,y           начало координат платы в системе САПР
            ├─ Profile             контур: Polygon (наружный) + Cutout×k (вырезы)
            ├─ PadStack×N          отверстия и площадки (см. ниже)
            ├─ Package×N           посадочные места
            ├─ Component×N         размещённые компоненты
            └─ LayerFeature×N      геометрия слоя (layerRef)
```

## Единицы и координаты

* `CadHeader@units` — `MILLIMETER`, `INCH` или `MICRON`. Altium: Metric → `MILLIMETER`. Оба словаря
  (`DictionaryStandard@units` и прочие) — проверяйте, что совпадают.
* Координаты **абсолютные** в системе САПР; начало платы — `Step/Datum`. Для ±80 мм платы Datum был (1270; 1270).
* Вид «сверху насквозь», Y вверх, положительный угол против часовой. Нижние слои и компоненты **не зеркалены** в
  координатах слоя; признак нижней стороны — `Layer@side="BOTTOM"`, `Component@layerRef` нижнего слоя и/или
  `Xform@mirror="true"`.

## Слои

`<Layer name layerFunction side polarity>`:

| layerFunction | что | пример имени Altium |
|---|---|---|
| `SIGNAL` | медь | Top Layer, Bottom Layer |
| `LEGEND` | шелкография | Top Overlay |
| `SOLDERMASK` | маска (геометрия — **вскрытия**, т. е. где маски нет) | Top Solder |
| `PASTEMASK` | паста | Top Paste |
| `DIELCORE` | диэлектрик (геометрии нет) | Dielectric 1 |
| `DOCUMENT` | механические/служебные (контуры компонентов, обозначения, сверловка для чертежа) | Mechanical 1, Top Designators, PCB_Contour |
| `DRILL` | сверловка | Drill Guide |

`side`: `TOP`, `BOTTOM`, `INTERNAL`, `NONE`, `BOTH`. `polarity`: `POSITIVE`/`NEGATIVE` (у нашего файла все POSITIVE;
негативный слой — «закрашено везде, кроме геометрии» — читатели **не** инвертируют).

Порядок и материалы — `Stackup/StackupGroup/StackupLayer@sequence` + `Spec@name` → `General/Property@text`.
Толщину верить с оговоркой: медь в стекапе — то, что ввёл дизайнер/умолчание САПР (у нас 0.035 при фактических 70 мкм).

## Геометрия слоя

```
LayerFeature@layerRef
 └─ Set@net                      цепь (“No Net” или имя; без net — служебный Set с ColorRef)
     ├─ ColorRef
     ├─ Features
     │   ├─ Line@startX,startY,endX,endY  + LineDesc@lineWidth,lineEnd(ROUND|NONE|SQUARE),lineProperty
     │   ├─ Arc@startX,startY,endX,endY,centerX,centerY,clockwise  + LineDesc
     │   ├─ Contour ─ Polygon (PolyBegin, PolyStepSegment*, PolyStepCurve*) + Cutout*
     │   └─ UserSpecial ─ Line/Arc/…    контейнер-обёртка: геометрия внутри **на любой глубине**
     └─ Hole@x,y,diameter,platingStatus,name,plusTol,minusTol   (сверловка в слое)
```

* **Line** — дорожка с шириной `LineDesc@lineWidth` и концами `lineEnd` (обычно ROUND): это стадион, а не
  отрезок нулевой толщины.
* **Arc** — дуга дорожки; центр абсолютный; `clockwise="false"` ⇒ против часовой.
* **Contour** — залитый полигон (пролив, вскрытие маски): `Polygon` наружный, `Cutout` — дырки. Кольцо:
  `PolyBegin` (начало), затем `PolyStepSegment` (прямая к x,y) и `PolyStepCurve` (дуга к x,y вокруг
  `centerX,centerY`, `clockwise`). Кольцо замкнуто последней точкой = первой.
* **UserSpecial** — Altium кладёт туда линии/дуги шелкографии и документных слоёв; нельзя брать только прямых
  потомков `Features`, обходите дерево рекурсивно (`ipc2581.py` так и делает).
* В других САПР встречаются `Polyline`, `Circle`/`RectCenter` прямо в `Features`, `Text`, `Xform` со сдвигом и
  масштабом — Altium-экспорт их не содержит, читатель пропускает.

## PadStack: отверстия и площадки

```
PadStack@net                     одна «площадка с отверстием» (или просто площадка)
 ├─ LayerHole@name,diameter,platingStatus(PLATED|NONPLATED|VIA),x,y,plusTol,minusTol
 │   └─ Span@fromLayer,toLayer
 └─ LayerPad@layerRef            по одной на слой, где есть площадка
     ├─ Location@x,y
     ├─ StandardPrimitiveRef@id  → DictionaryStandard/EntryStandard
     ├─ Xform@rotation[,mirror]  (необязателен)
     └─ PinRef@componentRef,pin  (есть только у площадок компонентов — у переходных нет)
```

* Переходное: `platingStatus="VIA"`, **нет PinRef**. Отверстие крепежа/разъёма: PLATED/NONPLATED, PinRef указывает
  владельца (`componentRef`) — так находится «гайка», стойка M3, разъём.
* Отверстия лежат **и в `PadStack/LayerHole`, и в `LayerFeature/Set/Hole`** — одни и те же. Дедуплицируют по
  ключу (x, y, ⌀) с округлением до 1e-4 (первое вхождение побеждает). Python-версия при этом **округляет
  координаты до 1e-4** (0.499999 → 0.5).
* Площадки **отдельных слоёв** (`LayerPad`) — и есть медные площадки слоя: читатель кладёт их в цепь слоя как
  `Pad`. SMT-площадки без отверстия — тоже `PadStack` (без `LayerHole`).

## Компоненты, посадочные места, BOM

```
Package@name,type,height,pinOneOrientation
 ├─ Outline/Polygon (+LineDesc)   контур корпуса в ЛОКАЛЬНЫХ координатах
 └─ Pin@number,name,type,electricalType,mountType  ─ Location, StandardPrimitiveRef   (локальные координаты)

Component@refDes,packageRef,part,layerRef,mountType,height,standoff,weight
 ├─ Xform@rotation[,mirror]       поворот против часовой (градусы); mirror=true — нижняя сторона (зеркало по X)
 └─ Location@x,y                  точка привязки в координатах платы

Bom/BomItem@OEMDesignNumberRef,internalPartNumber,description,category,quantity,pinCount
 └─ RefDes@name,packageRef,layerRef ×quantity
```

* Положение вывода на плате: `Location(Component) + R(rotation) · (mirror? x→−x) · Location(Pin)` (порядок «зеркало,
  потом поворот» — **не проверен**: в нашем файле зеркальных компонентов нет); тот же вывод
  одновременно есть как `LayerPad` с `PinRef` — проще брать площадку оттуда (слой и цепь уже известны).
* `Component@height` — высота над платой, `standoff` — зазор под корпусом: нужны для оценки высоких деталей (параллакс
  камеры, коллизии, зазоры).
* BOM связан с компонентами по `RefDes@name`.

## Быстрые запросы на Python

```python
import ipc2581 as ipc
b = ipc.load("board.cvg"); dx, dy = b.datum
top = b.layers["Top Layer"]                       # {net: [Line|Arc|Poly|Pad, ...]}
pours = [p for net, items in top.items() for p in items if isinstance(p, ipc.Poly)]
vias  = [h for h in b.holes if h.plated == "VIA"]  # Hole(x, y, d, plated, name) — без вычета Datum!
pads_of_R1 = [(net, p) for net, items in top.items() for p in items
              if isinstance(p, ipc.Pad) and p.pin.startswith("R1-")]
```

Ring-формат полигона: `[("M", x, y), ("L", x, y), ("A", x, y, cx, cy, ccw), …]`; `Poly.rings[0]` — наружный, остальные — вырезы.
Форма площадки `Pad.shape`: `("circle", d)`, `("rect", w, h)`, `("poly", Poly)` — в локальных координатах, повернуть на `Pad.rot`.
