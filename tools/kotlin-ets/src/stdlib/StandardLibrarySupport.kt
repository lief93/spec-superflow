package dev.ets

internal data class SupportFunction(val symbol: String, val source: String, val dependencies: List<String> = emptyList())

// Pinned target runtime, in stable dependency-before-consumer order. Bodies do not depend on input IR.
private val supportFunctions = exceptionSupportFunctions + collectionSupportFunctions + listOf(
    SupportFunction("stdlib:__etsIntArrayHash", """
        function __etsIntArrayHash(values: Array<number> | null): number {
          if (values === null) { return 0; }
          let hash = 1;
          for (const value of values) { hash = (Math.imul(hash, 31) + value) | 0; }
          return hash;
        }
    """.trimIndent()),
    SupportFunction("stdlib:__etsIntArrayString", """
        function __etsIntArrayString(values: Array<number> | null): string {
          return values === null ? 'null' : '[' + values.join(', ') + ']';
        }
    """.trimIndent()),
    SupportFunction("stdlib:__etsFloatHash", """
        function __etsFloatHash(value: number): number {
          if (Number.isNaN(value)) { return 2143289344; }
          const bits = new DataView(new ArrayBuffer(4));
          bits.setFloat32(0, value);
          return bits.getInt32(0);
        }
    """.trimIndent()),
    SupportFunction("stdlib:__etsDoubleHash", """
        function __etsDoubleHash(value: number): number {
          if (Number.isNaN(value)) { return 2146959360; }
          const bits = new DataView(new ArrayBuffer(8));
          bits.setFloat64(0, value);
          return bits.getInt32(0) ^ bits.getInt32(4);
        }
    """.trimIndent()),
    SupportFunction("stdlib:__etsFloatingCompare", """
        function __etsFloatingCompare(left: number, right: number): number {
          if (left < right) { return -1; }
          if (left > right) { return 1; }
          if (left === right) {
            if (left === 0 && 1 / left !== 1 / right) { return 1 / left < 0 ? -1 : 1; }
            return 0;
          }
          return Number.isNaN(left) ? (Number.isNaN(right) ? 0 : 1) : -1;
        }
    """.trimIndent()),
    SupportFunction("stdlib:__etsStringHash", """
        function __etsStringHash(value: string): number {
          let hash = 0;
          for (let index = 0; index < value.length; index++) {
            hash = (Math.imul(hash, 31) + value.charCodeAt(index)) | 0;
          }
          return hash;
        }
    """.trimIndent()),
    SupportFunction("stdlib:__etsIntDiv", """
        function __etsIntDiv(a: number, b: number): number {
          if (b === 0) { throw new __etsThrowable('ArithmeticException', 'ArithmeticException: / by zero'); }
          return Math.trunc(a / b) | 0;
        }
    """.trimIndent(), listOf("stdlib:__etsThrowable")),
    SupportFunction("stdlib:__etsIntRem", """
        function __etsIntRem(a: number, b: number): number {
          if (b === 0) { throw new __etsThrowable('ArithmeticException', 'ArithmeticException: / by zero'); }
          return (a % b) | 0;
        }
    """.trimIndent(), listOf("stdlib:__etsThrowable")),
    SupportFunction("stdlib:__etsListGet", """
        function __etsListGet<T>(values: Array<T>, index: number): T {
          if (index < 0 || index >= values.length) { throw new __etsThrowable('IndexOutOfBoundsException', 'IndexOutOfBoundsException'); }
          return values[index];
        }
    """.trimIndent(), listOf("stdlib:__etsThrowable")),
    SupportFunction("stdlib:__etsListAdd", """
        function __etsListAdd<T>(values: Array<T>, value: T): boolean {
          values.push(value);
          return true;
        }
    """.trimIndent()),
    SupportFunction("stdlib:__etsListMap", """
        function __etsListMap<T, R>(values: Array<T>, transform: (value: T) => R): Array<R> {
          const size = values.length;
          const result: Array<R> = [];
          for (let index = 0; index < size; index++) {
            result.push(transform(values[index]));
            if (values.length !== size) { throw new __etsThrowable('ConcurrentModificationException', 'ConcurrentModificationException'); }
          }
          return result;
        }
    """.trimIndent(), listOf("stdlib:__etsThrowable")),
    SupportFunction("stdlib:__etsListFilter", """
        function __etsListFilter<T>(values: Array<T>, predicate: (value: T) => boolean, keep: boolean): Array<T> {
          const size = values.length;
          const result: Array<T> = [];
          for (let index = 0; index < size; index++) {
            const element = values[index];
            if (predicate(element) === keep) { result.push(element); }
            if (values.length !== size) { throw new __etsThrowable('ConcurrentModificationException', 'ConcurrentModificationException'); }
          }
          return result;
        }
    """.trimIndent(), listOf("stdlib:__etsThrowable")),
    SupportFunction("stdlib:__etsIllegalArgumentException", """
        function __etsIllegalArgumentException(message: string): never {
          throw new __etsThrowable('IllegalArgumentException', 'IllegalArgumentException: ' + message);
        }
    """.trimIndent(), listOf("stdlib:__etsThrowable")),
    SupportFunction("stdlib:__etsProgressionLastElement", """
        function __etsProgressionLastElement(start: number, end: number, step: number): number {
          const mod = (value: number, divisor: number): number => {
            const remainder = value % divisor;
            return remainder >= 0 ? remainder : (remainder + divisor) | 0;
          };
          const differenceModulo = (a: number, b: number, c: number): number => {
            return mod((mod(a, c) - mod(b, c)) | 0, c);
          };
          if (step > 0) { return start >= end ? end : (end - differenceModulo(end, start, step)) | 0; }
          if (step < 0) { return start <= end ? end : (end + differenceModulo(start, end, (-step) | 0)) | 0; }
          return __etsIllegalArgumentException('Step is zero.');
        }
    """.trimIndent(), listOf("stdlib:__etsIllegalArgumentException")),
    SupportFunction("stdlib:__etsStringGet", """
        function __etsStringGet(value: string, index: number): string {
          if (index < 0 || index >= value.length) { throw new __etsThrowable('IndexOutOfBoundsException', 'IndexOutOfBoundsException'); }
          return value.charAt(index);
        }
    """.trimIndent(), listOf("stdlib:__etsThrowable")),
    SupportFunction("stdlib:__etsSubstring", """
        function __etsSubstring(value: string, start: number, end: number): string {
          if (start < 0 || end > value.length || start > end) { throw new __etsThrowable('IndexOutOfBoundsException', 'IndexOutOfBoundsException'); }
          return value.substring(start, end);
        }
    """.trimIndent(), listOf("stdlib:__etsThrowable")),
    SupportFunction("stdlib:__etsSubstringFrom", """
        function __etsSubstringFrom(value: string, start: number): string {
          return __etsSubstring(value, start, value.length);
        }
    """.trimIndent(), listOf("stdlib:__etsSubstring")),
    SupportFunction("stdlib:__etsIterator", """
        class __etsIterator<T> {
          readonly more: () => boolean;
          readonly take: () => T;
          constructor(more: () => boolean, take: () => T) { this.more = more; this.take = take; }
          hasNext(): boolean { return this.more(); }
          next(): T { return this.take(); }
        }
    """.trimIndent()),
    SupportFunction("stdlib:__etsArrayIterator", """
        function __etsArrayIterator<T>(values: Array<T>, failFast: boolean): __etsIterator<T> {
          const expectedSize = values.length;
          let index = 0;
          return new __etsIterator<T>(() => index !== values.length, () => {
            if (failFast && values.length !== expectedSize) { throw new __etsThrowable('ConcurrentModificationException', 'ConcurrentModificationException'); }
            if (index >= values.length) { throw new __etsThrowable('NoSuchElementException', 'NoSuchElementException'); }
            return values[index++];
          });
        }
    """.trimIndent(), listOf("stdlib:__etsThrowable", "stdlib:__etsIterator")),
    SupportFunction("stdlib:__etsListAny", """
        function __etsListAny<T>(values: Array<T>, predicate: (value: T) => boolean, match: boolean): boolean {
          const iterator = __etsArrayIterator(values, true);
          while (iterator.hasNext()) {
            if (predicate(iterator.next()) === match) { return true; }
          }
          return false;
        }
    """.trimIndent(), listOf("stdlib:__etsArrayIterator")),
    SupportFunction("stdlib:__etsListCount", """
        function __etsListCount<T>(values: Array<T>, predicate: (value: T) => boolean): number {
          const iterator = __etsArrayIterator(values, true);
          let count = 0;
          while (iterator.hasNext()) {
            if (predicate(iterator.next())) {
              count++;
              if (count > 2147483647) { throw new __etsThrowable('ArithmeticException', 'ArithmeticException: Count overflow has happened.'); }
            }
          }
          return count;
        }
    """.trimIndent(), listOf("stdlib:__etsThrowable", "stdlib:__etsArrayIterator")),
    SupportFunction("stdlib:__etsArrayGet", """
        function __etsArrayGet<T>(values: Array<T>, index: number): T {
          if (index < 0 || index >= values.length) { throw new __etsThrowable('ArrayIndexOutOfBoundsException', 'ArrayIndexOutOfBoundsException'); }
          return values[index];
        }
    """.trimIndent(), listOf("stdlib:__etsThrowable")),
    SupportFunction("stdlib:__etsArraySet", """
        function __etsArraySet<T>(values: Array<T>, index: number, value: T): void {
          if (index < 0 || index >= values.length) { throw new __etsThrowable('ArrayIndexOutOfBoundsException', 'ArrayIndexOutOfBoundsException'); }
          values[index] = value;
        }
    """.trimIndent(), listOf("stdlib:__etsThrowable")),
    SupportFunction("stdlib:__etsIntProgression", """
        class __etsIntProgression {
          readonly first: number;
          readonly last: number;
          readonly step: number;
          constructor(first: number, end: number, step: number) {
            if (step === 0) { __etsIllegalArgumentException('Step must be non-zero.'); }
            if (step === -2147483648) { __etsIllegalArgumentException('Step must be greater than Int.MIN_VALUE to avoid overflow on negation.'); }
            this.first = first;
            this.last = __etsProgressionLastElement(first, end, step);
            this.step = step;
          }
        }
    """.trimIndent(), listOf("stdlib:__etsProgressionLastElement")),
    SupportFunction("stdlib:__etsIntProgressionCreate", """
        function __etsIntProgressionCreate(first: number, end: number, step: number): __etsIntProgression {
          return new __etsIntProgression(first, end, step);
        }
    """.trimIndent(), listOf("stdlib:__etsIntProgression")),
    SupportFunction("stdlib:__etsIntUntil", """
        function __etsIntUntil(first: number, end: number): __etsIntProgression {
          return end === -2147483648 ? new __etsIntProgression(1, 0, 1) : new __etsIntProgression(first, (end - 1) | 0, 1);
        }
    """.trimIndent(), listOf("stdlib:__etsIntProgression")),
    SupportFunction("stdlib:__etsIntStep", """
        function __etsIntStep(values: __etsIntProgression, step: number): __etsIntProgression {
          if (step <= 0) { __etsIllegalArgumentException('Step must be positive, was: ' + step.toString() + '.'); }
          return new __etsIntProgression(values.first, values.last, values.step > 0 ? step : -step);
        }
    """.trimIndent(), listOf("stdlib:__etsIntProgression")),
    SupportFunction("stdlib:__etsIntReverse", """
        function __etsIntReverse(values: __etsIntProgression): __etsIntProgression {
          return new __etsIntProgression(values.last, values.first, -values.step);
        }
    """.trimIndent(), listOf("stdlib:__etsIntProgression")),
    SupportFunction("stdlib:__etsProgressionIterator", """
        function __etsProgressionIterator(values: __etsIntProgression): __etsIterator<number> {
          let more = values.step > 0 ? values.first <= values.last : values.first >= values.last;
          let next = more ? values.first : values.last;
          return new __etsIterator<number>(() => more, () => {
            const value = next;
            if (value === values.last) {
              if (!more) { throw new __etsThrowable('NoSuchElementException', 'NoSuchElementException'); }
              more = false;
            } else { next = (next + values.step) | 0; }
            return value;
          });
        }
    """.trimIndent(), listOf("stdlib:__etsThrowable", "stdlib:__etsIntProgression", "stdlib:__etsIterator")),
)

// Compatibility for the UI text emitter, which does not expose its complete typed tree yet.
internal fun standardLibrarySupportLines(): List<String> = supportFunctions.flatMap { it.source.lines() }

internal fun standardLibrarySupportLines(requiredSymbols: Set<String>): List<String> {
    val selected = mutableSetOf<String>()
    fun include(symbol: String) {
        if (!selected.add(symbol)) return
        val function = requireNotNull(supportFunctions.find { it.symbol == symbol }) {
            "Unknown standard library runtime symbol: $symbol"
        }
        function.dependencies.forEach(::include)
    }
    requiredSymbols.forEach(::include)
    return supportFunctions.filter { it.symbol in selected }.flatMap { it.source.lines() }
}
