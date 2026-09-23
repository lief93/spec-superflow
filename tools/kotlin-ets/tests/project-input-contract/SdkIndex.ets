import { ProjectInputPage } from './Page';
import { colorInput, dependencyInput, dimensionInput, fontInput, imageInput, stringInput, tokenInput } from './Values';

@Entry
@Component
struct SdkIndex {
  build() {
    Column() {
      ProjectInputPage()
      if (tokenInput()) {
        Text(stringInput())
          .fontColor(colorInput())
          .fontFamily(fontInput())
          .fontSize(dimensionInput())
        Image(imageInput()).width(dimensionInput())
        Text(dependencyInput())
      }
    }
  }
}
