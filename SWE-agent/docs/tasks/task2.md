Given an integer array nums and an integer k.
Return the length of the longest contiguous subarray such that the sum of its elements is **at most k**.

You must implement an algorithm that runs in O(n) time.

## Example 1:

> Input: nums = [1,2,1,0,1,1,0], k = 4
> Output: 5
> Explanation: The subarray [1,0,1,1,0] has sum 3 <= 4 and length 5 (one possible answer).

## Example 2:

> Input: nums = [5,1,1,1], k = 3
> Output: 3
> Explanation: The longest valid subarray is [1,1,1] with sum 3.

## Example 3:

> Input: nums = [2,2,2], k = 1
> Output: 0
> Explanation: No non-empty subarray can have sum <= 1, so the answer is 0.

## Constraints:

1 <= nums.length <= 10^5  
-10^4 <= nums[i] <= 10^4  
-10^9 <= k <= 10^9
