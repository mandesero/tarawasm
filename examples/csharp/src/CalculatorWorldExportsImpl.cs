namespace CalculatorWorld;

public partial class CalculatorWorldExportsImpl : ICalculatorWorldExports
{
    public static int Add(int left, int right) => left + right;
    public static string Echo(string value) => value;
}
