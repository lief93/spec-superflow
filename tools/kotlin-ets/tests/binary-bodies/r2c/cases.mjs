export const seeds = [1, -2, 2147483647];
export const expected = ['4/25/1/3/3/2/RCDRVCNCD', '1/22/-2/3/3/2/RCDRVCNCD',
  '-2147483646/-2147483625/2147483647/3/3/2/RCDRVCNCD'];
export const layouts = [['combined', ['combined.jar']], ['second-jar', ['entry.jar', 'helper.jar']]];
export const boundaries = [
  ['signature', ['signature.jar'], 'Application.kt', 'signature-only', /JVM binary metadata contains no serialized IR/],
  ['missing-body', ['entry.jar', 'signature-helper.jar'], 'Application.kt', 'missing serialized IR body for dependency', /missing serialized IR body for dependency.*defaultHelper/],
  ['missing-jar', ['entry.jar'], 'Application.kt', 'unlinked serialized dependencies:', /unlinked serialized dependencies:.*defaultHelper/],
  ['unused-default-body', ['entry.jar', 'signature-helper.jar'], 'ExplicitOnly.kt', 'missing serialized IR body for dependency', /missing serialized IR body for dependency.*defaultHelper/],
  ['unused-default-jar', ['entry.jar'], 'ExplicitOnly.kt', 'unlinked serialized dependencies:', /unlinked serialized dependencies:.*defaultHelper/],
];
