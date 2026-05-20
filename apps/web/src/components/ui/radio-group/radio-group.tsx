// shadcn/ui の RadioGroup セット。
// 公式: https://ui.shadcn.com/docs/components/radio-group
//
// RadioGroup: 排他選択のグループ全体。中の RadioGroupItem を 1 つだけ選べる状態に揃える。
// RadioGroupItem: 個々の選択肢。クリック / 矢印キーで選択を移せる（Radix が a11y を担保）。
//   見た目は「中央に丸を表示する円」だが、本プロジェクトでは選択肢全体をカード状に
//   ラップして使うことが多いため、Item 自体は最小限の装飾に留め、外側スタイルは
//   呼び出し側の <label> で当てる（data-[state=checked] を当てやすくするため）。
"use client";

import * as RadioGroupPrimitive from "@radix-ui/react-radio-group";
import { Circle } from "lucide-react";
import * as React from "react";

import { cn } from "@/lib/utils";

export const RadioGroup = React.forwardRef<
  React.ElementRef<typeof RadioGroupPrimitive.Root>,
  React.ComponentPropsWithoutRef<typeof RadioGroupPrimitive.Root>
>(({ className, ...props }, ref) => {
  return <RadioGroupPrimitive.Root ref={ref} className={cn("grid gap-2", className)} {...props} />;
});
RadioGroup.displayName = RadioGroupPrimitive.Root.displayName;

export const RadioGroupItem = React.forwardRef<
  React.ElementRef<typeof RadioGroupPrimitive.Item>,
  React.ComponentPropsWithoutRef<typeof RadioGroupPrimitive.Item>
>(({ className, ...props }, ref) => {
  return (
    <RadioGroupPrimitive.Item
      ref={ref}
      className={cn(
        "aspect-square h-4 w-4 rounded-full border border-primary text-primary shadow ring-offset-background focus:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50",
        className,
      )}
      {...props}
    >
      <RadioGroupPrimitive.Indicator className="flex items-center justify-center">
        {/* Circle: 選択された時だけ表示される中の点（lucide のアイコン、fill で塗りつぶす）。 */}
        <Circle className="h-2.5 w-2.5 fill-current text-current" />
      </RadioGroupPrimitive.Indicator>
    </RadioGroupPrimitive.Item>
  );
});
RadioGroupItem.displayName = RadioGroupPrimitive.Item.displayName;
