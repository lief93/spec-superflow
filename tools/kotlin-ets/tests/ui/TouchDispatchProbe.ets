// Manually authored native API diagnostic, not source-to-ETS acceptance.
function nearestChild(items: TouchTestInfo[], inset: number, width: number, height: number): TouchResult {
  let selected: string = '';
  let best: number = Number.POSITIVE_INFINITY;
  for (let index = 0; index < items.length; index++) {
    const item = items[index];
    const x = item.x - inset;
    const y = item.y - inset;
    const dx = Math.max(0, -x, x - width);
    const dy = Math.max(0, -y, y - height);
    if (dx <= Math.max(0, (48 - width) / 2) && dy <= Math.max(0, (48 - height) / 2)) {
      const distance = dx * dx + dy * dy;
      if (distance < best) {
        selected = item.id;
        best = distance;
      }
    }
  }
  return selected.length > 0 ? { strategy: TouchTestStrategy.FORWARD, id: selected }
    : { strategy: TouchTestStrategy.DEFAULT };
}

@Entry
@Component
struct TouchDispatchProbe {
  @State selected: number = -1;
  @State hits: number = 0;

  build() {
    Column() {
      Row() {
        ForEach([0, 1, 2, 3], (index: number) => {
          Stack({ alignContent: Alignment.TopStart }) {
            Stack() {}
              .width(20).height(8).backgroundColor(Color.Black).id('paint-' + index)
              .responseRegion({ x: -14, y: -20, width: 48, height: 48 })
              .onClick(() => { this.selected = index; this.hits++; })
          }.padding(4).id('target-' + index)
            .responseRegion({ x: -10, y: -16, width: 48, height: 48 })
        })
      }.padding(8).id('touch-row')
        .responseRegion({ x: -2, y: -8, width: 'calc(100% + 4vp)', height: 'calc(100% + 16vp)' })
        .onChildTouchTest((items: TouchTestInfo[]) => nearestChild(items, 4, 20, 8))
      Text('Selected ' + this.selected + ' Hits ' + this.hits).id('result')
    }.padding(40).alignItems(HorizontalAlign.Start).width('100%').height('100%')
  }
}
