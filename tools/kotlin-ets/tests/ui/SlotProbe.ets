// Native slot syntax/layout probe, not generated transcription acceptance.
@Entry
@Component
struct SlotProbe {
  @Builder
  Pair(prefix: string) {
    Text('one').id(prefix + '-one').width(40).height(20)
    Text('two').id(prefix + '-two').width(40).height(20)
  }

  @Builder
  VerticalFrame(content: WrappedBuilder<[]>) {
    Column() {
      Text('before').id('column-before').width(40).height(20)
      content.builder()
      Text('after').id('column-after').width(40).height(20)
    }.alignItems(HorizontalAlign.Start)
  }

  @Builder
  HorizontalFrame(content: WrappedBuilder<[]>) {
    Row() {
      Text('before').id('row-before').width(40).height(20)
      content.builder()
      Text('after').id('row-after').width(40).height(20)
    }.alignItems(VerticalAlign.Top)
  }

  build() {
    Column() {
      this.VerticalFrame(new WrappedBuilder<[]>(() => { this.Pair('column') }))
      this.HorizontalFrame(new WrappedBuilder<[]>(() => { this.Pair('row') }))
    }.alignItems(HorizontalAlign.Start).width('100%').height('100%')
  }
}
