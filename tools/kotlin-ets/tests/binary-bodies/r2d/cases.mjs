export const seeds = [1, -2, 2147483647];
export const expected = ['115/231/122/227/6/IiDBdBInDe', '109/233/119/229/6/IiDBdBInDe',
  '111/231/-2147483528/227/6/IiDBdBInDe'];
export const layouts = [['combined', ['combined.jar']], ['split', ['int.jar', 'double.jar']],
  ['reversed', ['double.jar', 'int.jar']]];
export const boundaries = [
  ['selected-signature-only', ['int.jar', 'signature-double.jar'], 'signature-only', /JVM binary metadata contains no serialized IR/],
  ['selected-helper-no-body', ['entries.jar', 'int-helper.jar', 'signature-double-helper.jar'],
    'missing serialized IR body for dependency', /missing serialized IR body for dependency.*DoubleHelperKt/],
  ['selected-helper-missing', ['entries.jar', 'int-helper.jar'],
    'unlinked serialized dependencies:', /unlinked serialized dependencies:.*helper.*kotlin.Double/],
];
