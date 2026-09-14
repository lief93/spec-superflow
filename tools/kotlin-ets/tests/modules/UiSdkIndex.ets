import { CaptionCard } from '../modules/CaptionCard';
import { QuietCard } from '../modules/QuietCard';
import { DerivedCaption } from '../modules/DerivedCaption';
import { captionValue } from '../modules/CaptionValue';

@Entry
@Component
struct Index {
  build() {
    Column() {
      CaptionCard()
      QuietCard()
      Text(captionValue(new DerivedCaption()).toString())
    }
  }
}
