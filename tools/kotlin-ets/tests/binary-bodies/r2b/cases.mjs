export const seeds = [1, -2, 2147483647];
export const expected = [
  '8/22/7/3/3/RADRAENAI/8/22',
  '5/19/1/3/3/RADRAENAI/5/19',
  '-2147483642/-2147483628/3/3/3/RADRAENAI/-2147483642/-2147483628',
];
export const layouts = [
  ['combined', ['combined.jar']],
  ['second-jar', ['entry.jar', 'helper.jar']],
];
export const boundaries = [
  ['signature', ['signature.jar'], 'Application.kt', 'signature-only', /JVM binary metadata contains no serialized IR/],
  ['missing-body', ['entry.jar', 'signature-helper.jar'], 'Application.kt', 'missing serialized IR body for dependency', /missing serialized IR body for dependency.*extHelper/],
  ['missing-jar', ['entry.jar'], 'Application.kt', 'unlinked serialized dependencies:', /unlinked serialized dependencies:.*extHelper/],
  ['missing-source', ['entry.jar', 'no-source-helper.jar'], 'Application.kt', 'no SourceFile attribute', /no SourceFile attribute.*no-source-helper.jar/],
  ['reified', ['Reified.jar'], 'ReifiedApplication.kt', 'unsupported reified binary inline dependency', /unsupported reified binary inline dependency/],
  ['member', ['Member.jar'], 'MemberApplication.kt', 'members are unsupported', /members are unsupported/],
  ['constructor', ['Constructor.jar'], 'ConstructorApplication.kt', 'unlinked serialized dependencies:', /unlinked serialized dependencies:.*Artifact/],
  ['multifile', ['Multifile.jar'], 'MultifileApplication.kt', 'unsupported serialized dependency format MULTIFILE_CLASS_PART', /unsupported serialized dependency format MULTIFILE_CLASS_PART/],
];
