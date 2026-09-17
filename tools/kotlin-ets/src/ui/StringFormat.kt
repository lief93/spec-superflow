package dev.ets

internal val stringFormatType = EtsFunctionType(listOf(EtsTypes.NUMBER,
    EtsNamedType("Array", listOf(EtsTypes.OBJECT))), EtsTypes.STRING)

/** Delegate resource selection and the supported format syntax to the native resource manager. */
internal val stringFormatSupport = """
function __etsFormatString(id: number, args: Array<Object>): string {
  const values: Array<string | number> = [];
  for (const value of args) {
    if (typeof value === 'string' || typeof value === 'number') {
      values.push(value);
    } else {
      throw new Error('String resource formatting requires string or number arguments');
    }
  }
  return getContext().resourceManager.getStringSync(id, ...values);
}
""".trimIndent().lines()
