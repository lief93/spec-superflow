@Entry
@Component
struct Index {
  @State private message: string = '__PROJECT_NAME__ migration ready';

  build() {
    Column({ space: 16 }) {
      Text(this.message)
        .fontSize(24)
        .fontWeight(FontWeight.Bold)
      Text('Replace this page with migrated ArkUI features.')
        .fontSize(16)
        .fontColor('#5F6368')
    }
    .width('100%')
    .height('100%')
    .justifyContent(FlexAlign.Center)
    .padding(24)
  }
}
