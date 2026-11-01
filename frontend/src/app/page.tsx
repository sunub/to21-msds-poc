import Link from "next/link";

export default function HomePage() {
  return (
    <main className="mx-auto max-w-page px-8 py-14">
      <h1 className="text-2xl font-bold">MSDS 검수</h1>
      <p className="mt-2 text-mut">검수 화면은 3주차에 이 폴더에서 만듭니다.</p>
      <p className="mt-6">
        <Link href="/design-system/">디자인 시스템 보기</Link>
      </p>
    </main>
  );
}
