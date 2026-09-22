package dev.ets

internal val stringFormatType = EtsFunctionType(listOf(EtsTypes.NUMBER,
    EtsNamedType("Array", listOf(EtsTypes.OBJECT))), EtsTypes.STRING)
internal val pluralFormatType = EtsFunctionType(listOf(EtsTypes.NUMBER, EtsTypes.NUMBER,
    EtsNamedType("Array", listOf(EtsTypes.OBJECT))), EtsTypes.STRING)

/** Delegate resource selection and the supported format syntax to the native resource manager. */
internal val stringFormatSupport = """
function __etsStringFormatValues(args: Array<Object>): Array<string | number> {
  const values: Array<string | number> = [];
  for (const value of args) {
    if (typeof value === 'string' || typeof value === 'number') {
      values.push(value);
    } else {
      throw new Error('String resource formatting requires string or number arguments');
    }
  }
  return values;
}

function __etsFormatString(id: number, args: Array<Object>): string {
  const values = __etsStringFormatValues(args);
  return getContext().resourceManager.getStringSync(id, ...values);
}
""".trimIndent().lines()

internal val pluralFormatSupport = """
function __etsFormatPlural(id: number, quantity: number, args: Array<Object>): string {
  const values = __etsStringFormatValues(args);
  return getContext().resourceManager.getPluralStringValueSync(id, quantity, ...values);
}
""".trimIndent().lines()
