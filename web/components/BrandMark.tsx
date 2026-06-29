export default function BrandMark({ compact = false }: { compact?: boolean }) {
  return (
    // Official public CarDuka brand asset. Plain img avoids Next image-domain coupling.
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src="https://www.carduka.com/images/logo.svg"
      alt="CarDuka"
      className={compact ? "h-7 w-auto" : "h-10 w-auto"}
    />
  );
}
