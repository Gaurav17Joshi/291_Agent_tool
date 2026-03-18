Given an unsorted integer array nums of length n containing **distinct** numbers in the range [0, n].
Return the single number in [0, n] that is not present in nums.

You must implement an algorithm that runs in O(n) time and uses O(1) auxiliary space.

## Example 1:

> Input: nums = [3,0,1]
> Output: 2
> Explanation: n = 3 and the numbers in [0,3] are {0,1,2,3}. The missing number is 2.

## Example 2:

> Input: nums = [0,1]
> Output: 2
> Explanation: n = 2 and the numbers in [0,2] are {0,1,2}. The missing number is 2.

## Example 3:

> Input: nums = [9,6,4,2,3,5,7,0,1]
> Output: 8
> Explanation: n = 9 and the missing number is 8.

## Constraints:

1 <= nums.length <= 10^5  
0 <= nums[i] <= nums.length  
All the numbers of nums are unique.
