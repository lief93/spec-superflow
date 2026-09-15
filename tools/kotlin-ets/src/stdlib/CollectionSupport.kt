package dev.ets

// ETS storage implements the same hash/equality/presence separation as Kotlin/JS.
// Native Map is used only for numeric hash buckets, never for source object equality.
internal val collectionSupportFunctions = listOf(
    SupportFunction("stdlib:__etsPair", """
        class __etsPair<K, V> {
          readonly first: K;
          readonly second: V;
          constructor(first: K, second: V) { this.first = first; this.second = second; }
        }
    """.trimIndent()),
    SupportFunction("stdlib:__etsMapEntry", """
        class __etsMapEntry<K, V> {
          readonly key: K;
          value: V;
          present: boolean = true;
          constructor(key: K, value: V) { this.key = key; this.value = value; }
        }
    """.trimIndent()),
    SupportFunction("stdlib:__etsMap", """
        class __etsMap<K, V> {
          buckets: Map<number, Array<__etsMapEntry<K, V>>> = new Map<number, Array<__etsMapEntry<K, V>>>();
          ordered: Array<__etsMapEntry<K, V>> = [];
          size: number = 0;
          version: number = 0;
          equal: (left: K, right: K) => boolean;
          hash: (key: K) => number;
          constructor(equal: (left: K, right: K) => boolean, hash: (key: K) => number, pairs: Array<__etsPair<K, V>>) {
            this.equal = equal;
            this.hash = hash;
            for (const pair of pairs) { this.put(pair.first, pair.second); }
          }
          find(key: K): __etsMapEntry<K, V> | null {
            const bucket = this.buckets.get(this.hash(key));
            if (bucket !== undefined) {
              for (const entry of bucket) { if (entry.present && this.equal(entry.key, key)) { return entry; } }
            }
            return null;
          }
          containsKey(key: K): boolean { return this.find(key) !== null; }
          containsValue(value: V, equal: (left: V, right: V) => boolean): boolean {
            for (const entry of this.ordered) { if (entry.present && equal(entry.value, value)) { return true; } }
            return false;
          }
          get(key: K): V | null { const entry = this.find(key); return entry === null ? null : entry.value; }
          put(key: K, value: V): V | null {
            const hash = this.hash(key);
            let bucket = this.buckets.get(hash);
            if (bucket === undefined) { bucket = []; this.buckets.set(hash, bucket); }
            for (const entry of bucket) {
              if (entry.present && this.equal(entry.key, key)) { const old = entry.value; entry.value = value; return old; }
            }
            const entry = new __etsMapEntry<K, V>(key, value);
            bucket.push(entry);
            this.ordered.push(entry);
            this.size++;
            this.version++;
            return null;
          }
          remove(key: K): V | null {
            const entry = this.find(key);
            if (entry === null) { return null; }
            entry.present = false;
            this.size--;
            this.version++;
            return entry.value;
          }
          clear(): void {
            if (this.size === 0) { return; }
            this.buckets.clear(); this.ordered = []; this.size = 0; this.version++;
          }
          isEmpty(): boolean { return this.size === 0; }
          iterator(): __etsIterator<__etsMapEntry<K, V>> {
            const version = this.version;
            let index = 0;
            const more = (): boolean => {
              if (version !== this.version) { const failure = new Error('ConcurrentModificationException'); failure.name = 'ConcurrentModificationException'; throw failure; }
              while (index < this.ordered.length && !this.ordered[index].present) { index++; }
              return index < this.ordered.length;
            };
            return new __etsIterator<__etsMapEntry<K, V>>(more, () => {
              if (!more()) { const failure = new Error('NoSuchElementException'); failure.name = 'NoSuchElementException'; throw failure; }
              return this.ordered[index++];
            });
          }
        }
    """.trimIndent(), listOf("stdlib:__etsPair", "stdlib:__etsMapEntry", "stdlib:__etsIterator")),
    SupportFunction("stdlib:__etsSet", """
        class __etsSet<T> {
          map: __etsMap<T, boolean>;
          constructor(equal: (left: T, right: T) => boolean, hash: (key: T) => number, values: Array<T>) {
            this.map = new __etsMap<T, boolean>(equal, hash, []);
            for (const value of values) { this.add(value); }
          }
          get size(): number { return this.map.size; }
          add(value: T): boolean { return this.map.put(value, true) === null; }
          contains(value: T): boolean { return this.map.containsKey(value); }
          remove(value: T): boolean { return this.map.remove(value) !== null; }
          clear(): void { this.map.clear(); }
          isEmpty(): boolean { return this.map.isEmpty(); }
          iterator(): __etsIterator<T> {
            const entries = this.map.iterator();
            return new __etsIterator<T>(() => entries.hasNext(), () => entries.next().key);
          }
        }
    """.trimIndent(), listOf("stdlib:__etsMap")),
)
